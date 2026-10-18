<#
.SYNOPSIS
    Phase 5 cart smoke test (PowerShell). Exercises every cart endpoint against a running API.

.DESCRIPTION
    Prerequisites (run from backend\, venv active):
        python -m scripts.seed_products     # catalogue (already done in Phase 4)
        python -m scripts.seed_coupons      # the coupons this test uses
        uvicorn app.main:app --reload       # API running on $BaseUrl

    The script registers two throwaway users (one for the main flow, one for
    isolation / second-cart checks), so it never touches your real accounts.
    Those two users stay in the database afterwards - harmless, leave them.
    It logs in twice per run, and /login is rate limited (5 per minute per IP),
    so avoid running it more than twice in a minute.

    Expected totals are computed here from the same three settings the API
    uses. If you changed GST_RATE / FREE_DELIVERY_THRESHOLD / DELIVERY_CHARGE
    in .env, pass the same values as parameters.

    -IncludeInactiveCheck additionally deactivates one seeded product through
    docker/psql, verifies it cannot be added, and ALWAYS reactivates it.

.EXAMPLE
    .\scripts\smoke_test_cart.ps1
    .\scripts\smoke_test_cart.ps1 -IncludeInactiveCheck
#>
param(
    [string]$BaseUrl = "http://localhost:8000",
    [double]$GstRate = 0.05,
    [double]$FreeDeliveryThreshold = 500,
    [double]$DeliveryCharge = 49,
    [switch]$IncludeInactiveCheck,
    [string]$DbContainer = "healthy-harvest-postgres",
    [string]$DbUser = "healthy_harvest",
    [string]$DbName = "healthy_harvest_db"
)

$ErrorActionPreference = "Stop"
$script:Pass = 0
$script:Fail = 0

# ---------------------------------------------------------------- helpers

function Invoke-Api {
    param([string]$Method, [string]$Path, [string]$Token, $Body)
    $params = @{ Uri = "$BaseUrl$Path"; Method = $Method; UseBasicParsing = $true }
    if ($Token) { $params.Headers = @{ Authorization = "Bearer $Token" } }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json)
        $params.ContentType = "application/json"
    }
    try {
        $r = Invoke-WebRequest @params
        $status = [int]$r.StatusCode
        $content = $r.Content
    }
    catch {
        $resp = $_.Exception.Response
        if ($null -eq $resp) { throw }   # connection problem, not an HTTP error
        $status = [int]$resp.StatusCode
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            $content = $_.ErrorDetails.Message
        }
        else {
            $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
            $content = $reader.ReadToEnd()
        }
    }
    $json = $null
    try { $json = $content | ConvertFrom-Json } catch { }
    [pscustomobject]@{ Status = $status; Body = $json }
}

function Check {
    param([string]$Name, [bool]$Condition, [string]$Detail = "")
    if ($Condition) {
        Write-Host "  PASS  $Name" -ForegroundColor Green
        $script:Pass++
    }
    else {
        Write-Host "  FAIL  $Name   $Detail" -ForegroundColor Red
        $script:Fail++
    }
}

function Section([string]$Title) { Write-Host ""; Write-Host "== $Title" -ForegroundColor Cyan }

function Near($a, $b) { [math]::Abs([double]$a - [double]$b) -lt 0.005 }

function Get-Expected {
    param([decimal]$Subtotal, [decimal]$Discount = 0)
    $taxable = $Subtotal - $Discount
    $gst = [math]::Round($taxable * [decimal]$GstRate, 2, [MidpointRounding]::AwayFromZero)
    if ($Subtotal -le 0 -or $taxable -ge [decimal]$FreeDeliveryThreshold) { $delivery = [decimal]0 }
    else { $delivery = [decimal]$DeliveryCharge }
    [pscustomobject]@{ Taxable = $taxable; Gst = $gst; Delivery = $delivery; Total = $taxable + $gst + $delivery }
}

function Check-Totals {
    param($Cart, [decimal]$Subtotal, [decimal]$Discount, [string]$Label)
    $e = Get-Expected $Subtotal $Discount
    $t = $Cart.totals
    Check "$Label subtotal = $Subtotal"          (Near $t.subtotal $Subtotal)        "got $($t.subtotal)"
    Check "$Label discount = $Discount"          (Near $t.discount $Discount)        "got $($t.discount)"
    Check "$Label taxable = $($e.Taxable)"       (Near $t.taxable_amount $e.Taxable) "got $($t.taxable_amount)"
    Check "$Label GST = $($e.Gst)"               (Near $t.gst $e.Gst)                "got $($t.gst)"
    Check "$Label delivery = $($e.Delivery)"     (Near $t.delivery_charge $e.Delivery) "got $($t.delivery_charge)"
    Check "$Label total = $($e.Total)"           (Near $t.total $e.Total)            "got $($t.total)"
    Check "$Label total = taxable + GST + delivery" (Near $t.total ($t.taxable_amount + $t.gst + $t.delivery_charge))
}

function New-TestUser {
    param([string]$Tag)
    $stamp = (Get-Date).ToString("yyyyMMddHHmmssfff")
    $email = "cartsmoke_${Tag}_$stamp@example.com"
    $phone = "9" + (Get-Random -Minimum 100000000 -Maximum 999999999)
    $password = "SecurePass1!"
    $reg = Invoke-Api POST "/api/auth/register" $null @{
        first_name = "Cart"; last_name = "Smoke$Tag"; email = $email
        phone_number = $phone; password = $password; confirm_password = $password
    }
    if ($reg.Status -ne 201) { throw "Could not register test user ${Tag}: HTTP $($reg.Status) $($reg.Body.message)" }
    $login = Invoke-Api POST "/api/auth/login" $null @{ email = $email; password = $password }
    if ($login.Status -ne 200) { throw "Could not log in test user ${Tag}: HTTP $($login.Status) $($login.Body.message)" }
    [pscustomobject]@{ Email = $email; Token = $login.Body.data.access_token }
}

function Get-ProductId([string]$Slug) {
    $r = Invoke-Api GET "/api/products/$Slug"
    if ($r.Status -ne 200) { throw "Product '$Slug' not found (HTTP $($r.Status)). Run: python -m scripts.seed_products" }
    $d = $r.Body.data
    if ($d.id) { return $d.id }
    if ($d.product.id) { return $d.product.id }
    throw "Product detail response for '$Slug' has no id field."
}

function Line([object]$Cart, [string]$Slug) { $Cart.items | Where-Object { $_.product.slug -eq $Slug } | Select-Object -First 1 }

# ---------------------------------------------------------------- setup

Section "Setup"
$health = Invoke-Api GET "/"
Check "API is up at $BaseUrl" ($health.Status -eq 200) "HTTP $($health.Status)"
if ($health.Status -ne 200) { Write-Host "Start the API first (uvicorn app.main:app --reload)." -ForegroundColor Yellow; exit 1 }

$A = New-TestUser "A"
$B = New-TestUser "B"
Check "registered + logged in user A and user B" ($A.Token -and $B.Token)

$cereal = Get-ProductId "multigrain-cereal"   # 249.00, stock 40
$ragi   = Get-ProductId "ragi-dosa-mix"       # 175.00, stock 8
$raisin = Get-ProductId "golden-raisins"      # 149.00, stock 0
$poha   = Get-ProductId "poha-ready-mix"      # 189.00, stock 55
$almond = Get-ProductId "premium-almonds"     # 599.00, stock 25

# ---------------------------------------------------------------- auth + empty

Section "Unauthenticated access"
foreach ($call in @(
        @{ M = "GET";    P = "/api/cart";                       B = $null },
        @{ M = "POST";   P = "/api/cart/items";                 B = @{ product_id = $cereal; quantity = 1 } },
        @{ M = "PATCH";  P = "/api/cart/items/$cereal";         B = @{ quantity = 1 } },
        @{ M = "DELETE"; P = "/api/cart/items/$cereal";         B = $null },
        @{ M = "DELETE"; P = "/api/cart";                       B = $null },
        @{ M = "POST";   P = "/api/cart/coupon";                B = @{ code = "WELCOME10" } },
        @{ M = "DELETE"; P = "/api/cart/coupon";                B = $null })) {
    $r = Invoke-Api $call.M $call.P $null $call.B
    Check "$($call.M) $($call.P) without token -> 401" ($r.Status -eq 401) "got $($r.Status)"
}
$r = Invoke-Api GET "/api/cart" "not.a.real.token"
Check "garbage token -> 401" ($r.Status -eq 401) "got $($r.Status)"

Section "1. Empty cart"
$r = Invoke-Api GET "/api/cart" $A.Token
Check "GET /api/cart -> 200" ($r.Status -eq 200) "got $($r.Status)"
Check "envelope has success/message/data" (($r.Body.success -eq $true) -and $r.Body.message -and $r.Body.data)
Check "no items, item_count 0" (($r.Body.data.items.Count -eq 0) -and ($r.Body.data.item_count -eq 0))
Check-Totals $r.Body.data 0 0 "empty cart"

# ---------------------------------------------------------------- add / update

Section "2. Add product (2 x Multigrain Cereal = 498, just under free delivery)"
$r = Invoke-Api POST "/api/cart/items" $A.Token @{ product_id = $cereal; quantity = 2 }
Check "add -> 200" ($r.Status -eq 200) "got $($r.Status) $($r.Body.message)"
$cart = $r.Body.data
$line = Line $cart "multigrain-cereal"
Check "line quantity 2, unit price 249, line subtotal 498" (($line.quantity -eq 2) -and (Near $line.unit_price 249) -and (Near $line.line_subtotal 498))
Check-Totals $cart 498 0 "after add"

Section "3. Add same product again (increments)"
$r = Invoke-Api POST "/api/cart/items" $A.Token @{ product_id = $cereal; quantity = 1 }
$cart = $r.Body.data
Check "still one line, quantity 3" (($cart.items.Count -eq 1) -and ((Line $cart "multigrain-cereal").quantity -eq 3))
Check-Totals $cart 747 0 "after increment (free delivery)"

Section "4. Update quantity (absolute)"
$itemId = (Line $cart "multigrain-cereal").id
$r = Invoke-Api PATCH "/api/cart/items/$itemId" $A.Token @{ quantity = 1 }
Check "patch -> 200" ($r.Status -eq 200) "got $($r.Status)"
$cart = $r.Body.data
Check "quantity set to exactly 1" ((Line $cart "multigrain-cereal").quantity -eq 1)
Check-Totals $cart 249 0 "after update"
Check "amount_for_free_delivery = threshold - 249" (Near $cart.totals.amount_for_free_delivery ([decimal]$FreeDeliveryThreshold - 249))

# ---------------------------------------------------------------- stock

Section "5. Stock limits (Ragi Dosa Mix has 8 in stock)"
$r = Invoke-Api POST "/api/cart/items" $A.Token @{ product_id = $ragi; quantity = 9 }
Check "add 9 of 8 -> 409" ($r.Status -eq 409) "got $($r.Status)"
Check "message names the limit" ($r.Body.message -like "*8*") $r.Body.message
$r = Invoke-Api POST "/api/cart/items" $A.Token @{ product_id = $ragi; quantity = 8 }
Check "add exactly 8 -> 200" ($r.Status -eq 200) "got $($r.Status)"
$cart = $r.Body.data
$ragiLine = Line $cart "ragi-dosa-mix"
$r = Invoke-Api POST "/api/cart/items" $A.Token @{ product_id = $ragi; quantity = 1 }
Check "one more on top of 8 -> 409" ($r.Status -eq 409) "got $($r.Status)"
Check "message mentions what is already in the cart" ($r.Body.message -like "*already have 8*") $r.Body.message
$r = Invoke-Api PATCH "/api/cart/items/$($ragiLine.id)" $A.Token @{ quantity = 9 }
Check "patch to 9 -> 409" ($r.Status -eq 409) "got $($r.Status)"
$r = Invoke-Api GET "/api/cart" $A.Token
Check "quantity unchanged after rejected patch" ((Line $r.Body.data "ragi-dosa-mix").quantity -eq 8)
Check "available_quantity reported on the line" ((Line $r.Body.data "ragi-dosa-mix").available_quantity -eq 8)
$r = Invoke-Api POST "/api/cart/items" $A.Token @{ product_id = $raisin; quantity = 1 }
Check "out-of-stock product -> 409" ($r.Status -eq 409) "got $($r.Status)"
Check "message says out of stock" ($r.Body.message -like "*out of stock*") $r.Body.message

Section "6. Invalid input"
$r = Invoke-Api POST "/api/cart/items" $A.Token @{ product_id = [guid]::NewGuid().ToString(); quantity = 1 }
Check "unknown product -> 404" ($r.Status -eq 404) "got $($r.Status)"
$r = Invoke-Api POST "/api/cart/items" $A.Token @{ product_id = $cereal; quantity = 0 }
Check "quantity 0 -> 422" ($r.Status -eq 422) "got $($r.Status)"
$r = Invoke-Api POST "/api/cart/items" $A.Token @{ product_id = "not-a-uuid"; quantity = 1 }
Check "malformed product id -> 422" ($r.Status -eq 422) "got $($r.Status)"
$r = Invoke-Api PATCH "/api/cart/items/$itemId" $A.Token @{ quantity = -3 }
Check "negative quantity -> 422" ($r.Status -eq 422) "got $($r.Status)"
$r = Invoke-Api PATCH "/api/cart/items/not-a-uuid" $A.Token @{ quantity = 1 }
Check "malformed item id -> 422" ($r.Status -eq 422) "got $($r.Status)"
$r = Invoke-Api POST "/api/cart/items" $A.Token @{ product_id = $cereal; quantity = 1; price = 0.01; discount = 999; user_id = [guid]::NewGuid().ToString() }
Check "extra price/discount/user_id fields are ignored" ($r.Status -eq 200 -and (Near (Line $r.Body.data "multigrain-cereal").unit_price 249)) "got $($r.Status)"
$cart = $r.Body.data
$itemId = (Line $cart "multigrain-cereal").id
$r = Invoke-Api PATCH "/api/cart/items/$itemId" $A.Token @{ quantity = 1 }   # back to 1 cereal

# ---------------------------------------------------------------- isolation

Section "7. User isolation"
$r = Invoke-Api GET "/api/cart" $B.Token
Check "user B starts with an empty cart" ($r.Body.data.items.Count -eq 0)
$r = Invoke-Api PATCH "/api/cart/items/$itemId" $B.Token @{ quantity = 5 }
Check "B cannot update A's item -> 404" ($r.Status -eq 404) "got $($r.Status)"
$r = Invoke-Api DELETE "/api/cart/items/$itemId" $B.Token
Check "B cannot delete A's item -> 404" ($r.Status -eq 404) "got $($r.Status)"
$r = Invoke-Api GET "/api/cart" $A.Token
Check "A's cart untouched (cereal 1, ragi 8)" (((Line $r.Body.data "multigrain-cereal").quantity -eq 1) -and ((Line $r.Body.data "ragi-dosa-mix").quantity -eq 8))

# ---------------------------------------------------------------- coupons (A: subtotal 1649)

Section "8. Coupons - valid (A subtotal = 249 + 8 x 175 = 1649)"
$r = Invoke-Api POST "/api/cart/coupon" $A.Token @{ code = "welcome10" }
Check "WELCOME10 (typed lowercase) -> 200" ($r.Status -eq 200) "got $($r.Status) $($r.Body.message)"
$cart = $r.Body.data
Check "coupon shows as applied" (($cart.coupon.code -eq "WELCOME10") -and ($cart.coupon.applied -eq $true))
Check-Totals $cart 1649 100 "WELCOME10 (10% capped at 100)"

$r = Invoke-Api GET "/api/cart" $A.Token
Check "coupon persists on the next GET (page reload)" ($r.Body.data.coupon.code -eq "WELCOME10")

$r = Invoke-Api POST "/api/cart/coupon" $A.Token @{ code = "BIG20" }
Check "applying BIG20 replaces WELCOME10" (($r.Status -eq 200) -and ($r.Body.data.coupon.code -eq "BIG20"))
Check-Totals $r.Body.data 1649 329.80 "BIG20 (20% of 1649)"

Section "9. Coupons - rejected"
foreach ($case in @(
        @{ Code = "NOSUCHCODE"; Expect = "Invalid coupon" },
        @{ Code = "EXPIRED50";  Expect = "expired" },
        @{ Code = "INACTIVE20"; Expect = "not active" },
        @{ Code = "USEDUP";     Expect = "usage limit" },
        @{ Code = "FUTURE15";   Expect = "not valid yet" })) {
    $r = Invoke-Api POST "/api/cart/coupon" $A.Token @{ code = $case.Code }
    Check "$($case.Code) -> 400" ($r.Status -eq 400) "got $($r.Status)"
    Check "$($case.Code) message contains '$($case.Expect)'" ($r.Body.message -like "*$($case.Expect)*") $r.Body.message
}
$r = Invoke-Api GET "/api/cart" $A.Token
Check "rejected codes did not disturb the applied coupon (still BIG20)" ($r.Body.data.coupon.code -eq "BIG20")

Section "10. Coupon stops qualifying when the cart shrinks (BIG20 needs 1500)"
$ragiLine = Line $r.Body.data "ragi-dosa-mix"
$r = Invoke-Api PATCH "/api/cart/items/$($ragiLine.id)" $A.Token @{ quantity = 1 }
$cart = $r.Body.data
Check "coupon stays attached but applied = false" (($cart.coupon.code -eq "BIG20") -and ($cart.coupon.applied -eq $false))
Check "message explains the minimum" ($cart.coupon.message -like "*minimum order*") $cart.coupon.message
Check-Totals $cart 424 0 "below BIG20 minimum (no discount)"
$r = Invoke-Api PATCH "/api/cart/items/$($ragiLine.id)" $A.Token @{ quantity = 8 }
Check "restoring the quantity re-activates the discount" (($r.Body.data.coupon.applied -eq $true) -and (Near $r.Body.data.totals.discount 329.80))

Section "11. Remove coupon (and again - idempotent)"
$r = Invoke-Api DELETE "/api/cart/coupon" $A.Token
Check "remove -> 200, coupon null, discount 0" (($r.Status -eq 200) -and ($null -eq $r.Body.data.coupon) -and (Near $r.Body.data.totals.discount 0))
$r = Invoke-Api DELETE "/api/cart/coupon" $A.Token
Check "removing again -> 200" ($r.Status -eq 200) "got $($r.Status)"

# ---------------------------------------------------------------- B: minimum order, post-discount delivery

Section "12. Coupon minimum order (B has one 189 item)"
$r = Invoke-Api POST "/api/cart/coupon" $B.Token @{ code = "WELCOME10" }
Check "coupon on an empty cart -> 400" ($r.Status -eq 400) "got $($r.Status)"
$r = Invoke-Api POST "/api/cart/items" $B.Token @{ product_id = $poha; quantity = 1 }
Check "B adds 1 x Poha Ready Mix" ($r.Status -eq 200)
foreach ($code in @("WELCOME10", "FLAT100", "BIG20")) {
    $r = Invoke-Api POST "/api/cart/coupon" $B.Token @{ code = $code }
    Check "$code below its minimum -> 400" (($r.Status -eq 400) -and ($r.Body.message -like "*minimum order*")) "got $($r.Status) $($r.Body.message)"
}

Section "13. Free delivery is judged AFTER the discount (B: 599 - 100 = 499 < 500)"
$r = Invoke-Api DELETE "/api/cart" $B.Token
Check "clear B's cart" ($r.Status -eq 200 -and $r.Body.data.items.Count -eq 0)
$r = Invoke-Api POST "/api/cart/items" $B.Token @{ product_id = $almond; quantity = 1 }
Check-Totals $r.Body.data 599 0 "almonds alone (free delivery)"
$r = Invoke-Api POST "/api/cart/coupon" $B.Token @{ code = "FLAT100" }
Check "FLAT100 -> 200" ($r.Status -eq 200) "got $($r.Status) $($r.Body.message)"
Check-Totals $r.Body.data 599 100 "FLAT100 (delivery now charged)"

# ---------------------------------------------------------------- remove / clear

Section "14. Remove item"
$r = Invoke-Api GET "/api/cart" $A.Token
$cart = $r.Body.data
$ragiLine = Line $cart "ragi-dosa-mix"
$r = Invoke-Api DELETE "/api/cart/items/$($ragiLine.id)" $A.Token
Check "remove ragi line -> 200" ($r.Status -eq 200) "got $($r.Status)"
Check "only the cereal line is left" (($r.Body.data.items.Count -eq 1) -and ((Line $r.Body.data "multigrain-cereal").quantity -eq 1))
Check-Totals $r.Body.data 249 0 "after remove"
$r = Invoke-Api DELETE "/api/cart/items/$($ragiLine.id)" $A.Token
Check "removing the same item again -> 404" ($r.Status -eq 404) "got $($r.Status)"

Section "15. Clear cart (also clears the coupon)"
$r = Invoke-Api POST "/api/cart/items" $A.Token @{ product_id = $almond; quantity = 2 }
$r = Invoke-Api POST "/api/cart/coupon" $A.Token @{ code = "WELCOME10" }
Check "coupon attached before clearing" ($r.Body.data.coupon.code -eq "WELCOME10")
$r = Invoke-Api DELETE "/api/cart" $A.Token
Check "clear -> 200, empty, no coupon" (($r.Status -eq 200) -and ($r.Body.data.items.Count -eq 0) -and ($null -eq $r.Body.data.coupon))
Check-Totals $r.Body.data 0 0 "cleared cart"
$r = Invoke-Api GET "/api/cart" $A.Token
Check "still empty on next GET" (($r.Body.data.items.Count -eq 0) -and ($null -eq $r.Body.data.coupon))

# ---------------------------------------------------------------- optional: inactive product

if ($IncludeInactiveCheck) {
    Section "16. Inactive product (temporarily deactivates 'poha-ready-mix', always restores it)"
    $sqlOff = "UPDATE products SET is_active = false WHERE slug = 'poha-ready-mix';"
    $sqlOn  = "UPDATE products SET is_active = true WHERE slug = 'poha-ready-mix';"
    try {
        docker exec $DbContainer psql -U $DbUser -d $DbName -c $sqlOff | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "docker/psql failed - is the container name right? (-DbContainer)" }
        $r = Invoke-Api POST "/api/cart/items" $A.Token @{ product_id = $poha; quantity = 1 }
        Check "adding an inactive product -> 404" ($r.Status -eq 404) "got $($r.Status)"
    }
    finally {
        docker exec $DbContainer psql -U $DbUser -d $DbName -c $sqlOn | Out-Null
        Write-Host "  (poha-ready-mix reactivated)" -ForegroundColor DarkGray
    }
}
else {
    Write-Host ""
    Write-Host "(Skipped inactive-product check - re-run with -IncludeInactiveCheck to include it.)" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------- tidy + summary

Invoke-Api DELETE "/api/cart" $A.Token | Out-Null
Invoke-Api DELETE "/api/cart" $B.Token | Out-Null

Write-Host ""
$color = "Green"
if ($script:Fail -gt 0) { $color = "Red" }
Write-Host ("RESULT: {0} passed, {1} failed" -f $script:Pass, $script:Fail) -ForegroundColor $color
if ($script:Fail -gt 0) { exit 1 }