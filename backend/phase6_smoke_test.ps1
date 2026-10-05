<#
Phase 6 smoke test - addresses, checkout, order history and cancellation,
against a RUNNING backend (default http://localhost:8000).

    cd backend
    # in one terminal:  uvicorn app.main:app --reload
    # in another:       .\phase6_smoke_test.ps1
    # optional:         .\phase6_smoke_test.ps1 -BaseUrl http://localhost:8000 -Coupon WELCOME10

Needs the seeded catalogue (python -m scripts.seed_products) and, for the
coupon steps, python -m scripts.seed_coupons. It registers two throw-away
users with random e-mails, so it can be re-run any number of times. It
creates real rows in your DEVELOPMENT database (users, addresses, orders)
and leaves the last order cancelled.

Exit code: 0 if every check passed, 1 otherwise.
#>
param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Coupon = "WELCOME10"
)

$ErrorActionPreference = "Stop"
$script:passed = 0
$script:failed = 0

function Invoke-Api {
    param([string]$Method, [string]$Path, $Body = $null, [string]$Token = "", [hashtable]$Headers = @{})
    $h = @{}
    foreach ($k in $Headers.Keys) { $h[$k] = $Headers[$k] }
    if ($Token) { $h["Authorization"] = "Bearer $Token" }
    $params = @{ Uri = "$BaseUrl$Path"; Method = $Method; Headers = $h; UseBasicParsing = $true }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 6)
        $params.ContentType = "application/json"
    }
    try {
        $resp = Invoke-WebRequest @params
        $status = [int]$resp.StatusCode
        $content = $resp.Content
    }
    catch {
        $r = $_.Exception.Response
        if ($null -eq $r) { throw }
        $status = [int]$r.StatusCode
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) { $content = $_.ErrorDetails.Message }
        else { $content = (New-Object System.IO.StreamReader($r.GetResponseStream())).ReadToEnd() }
    }
    $json = $null
    if ($content) { try { $json = $content | ConvertFrom-Json } catch { } }
    return [pscustomobject]@{ Status = $status; Json = $json; Raw = $content }
}

function Check {
    param([string]$Label, [bool]$Condition, [string]$Detail = "")
    if ($Condition) {
        $script:passed++
        Write-Host "  PASS  $Label" -ForegroundColor Green
    }
    else {
        $script:failed++
        Write-Host "  FAIL  $Label  $Detail" -ForegroundColor Red
    }
}

function Section([string]$Title) { Write-Host "`n=== $Title ===" -ForegroundColor Cyan }

function New-TestUser([string]$Label) {
    $suffix = [guid]::NewGuid().ToString("N").Substring(0, 10)
    $email = "smoke.$Label.$suffix@example.com"
    $password = "Smoke#Pass1234"
    $phone = "+9198" + (Get-Random -Minimum 10000000 -Maximum 99999999)
    $reg = Invoke-Api POST "/api/auth/register" @{
        first_name = "Smoke"; last_name = $Label; email = $email; phone_number = $phone
        password = $password; confirm_password = $password
    }
    if ($reg.Status -ne 201) { throw "Could not register $email : $($reg.Raw)" }
    $login = Invoke-Api POST "/api/auth/login" @{ email = $email; password = $password }
    if ($login.Status -ne 200) { throw "Could not log in $email : $($login.Raw)" }
    return [pscustomobject]@{ Email = $email; Token = $login.Json.data.access_token }
}

function New-Key { return "smoke-" + [guid]::NewGuid().ToString() }

$addressBody = @{
    full_name = "Smoke Tester"; phone_number = "9876543210"; address_line_1 = "12 MG Road"
    address_line_2 = "Flat 4"; city = "Pune"; state = "Maharashtra"; postal_code = "411001"
}

Section "0. Setup: two throw-away users and a product to buy"
$a = New-TestUser "A"
$b = New-TestUser "B"
Write-Host "  user A: $($a.Email)`n  user B: $($b.Email)"

$list = Invoke-Api GET "/api/products?page_size=50"
$product = $list.Json.data.products | Where-Object { $_.in_stock -eq $true } | Select-Object -First 1
if ($null -eq $product) { throw "No in-stock product found - run: python -m scripts.seed_products" }
Write-Host "  product: $($product.name) ($($product.id)) at $($product.price)"

Section "1. Authentication is required"
foreach ($call in @(
        @("GET", "/api/addresses"), @("GET", "/api/orders"),
        @("GET", "/api/orders/$([guid]::NewGuid())"), @("POST", "/api/orders/$([guid]::NewGuid())/cancel"))) {
    $r = Invoke-Api $call[0] $call[1]
    Check "$($call[0]) $($call[1]) without a token -> 401" ($r.Status -eq 401) "got $($r.Status)"
}
$r = Invoke-Api POST "/api/orders" @{ shipping_address_id = [guid]::NewGuid().ToString() } "" @{ "Idempotency-Key" = (New-Key) }
Check "POST /api/orders without a token -> 401" ($r.Status -eq 401) "got $($r.Status)"

Section "2. Addresses"
$bad = $addressBody.Clone(); $bad.postal_code = "12"
$r = Invoke-Api POST "/api/addresses" $bad $a.Token
Check "bad PIN code -> 422" ($r.Status -eq 422) "got $($r.Status)"
$r = Invoke-Api POST "/api/addresses" $addressBody $a.Token
Check "add an address -> 201" ($r.Status -eq 201) "got $($r.Status): $($r.Raw)"
$addrA = $r.Json.data
Check "first address is the default" ($addrA.is_default -eq $true)
Check "country is India" ($addrA.country -eq "India")
$r = Invoke-Api POST "/api/addresses" $addressBody $b.Token
$addrB = $r.Json.data
$r = Invoke-Api GET "/api/addresses" -Token $a.Token
Check "user A sees only their own address" (@($r.Json.data).Count -eq 1 -and $r.Json.data[0].id -eq $addrA.id)

Section "3. Fill the cart (qty 2, coupon $Coupon if it applies)"
Invoke-Api DELETE "/api/cart" $null $a.Token | Out-Null
$r = Invoke-Api POST "/api/cart/items" @{ product_id = $product.id; quantity = 2 } $a.Token
Check "add to cart -> 200" ($r.Status -eq 200) "got $($r.Status): $($r.Raw)"
$r = Invoke-Api POST "/api/cart/coupon" @{ code = $Coupon } $a.Token
$couponApplied = ($r.Status -eq 200)
if ($couponApplied) { Write-Host "  coupon $Coupon applied" } else { Write-Host "  coupon not applied ($($r.Json.message)) - continuing without it" }
$cart = (Invoke-Api GET "/api/cart" -Token $a.Token).Json.data
$cartTotal = [double]$cart.totals.total
Write-Host "  cart total shown to the customer: $cartTotal"

Section "4. Place the order"
$r = Invoke-Api POST "/api/orders" @{ shipping_address_id = $addrA.id } $a.Token
Check "missing Idempotency-Key -> 422" ($r.Status -eq 422) "got $($r.Status)"
$r = Invoke-Api POST "/api/orders" @{ shipping_address_id = $addrA.id } $a.Token @{ "Idempotency-Key" = "short" }
Check "malformed Idempotency-Key -> 400" ($r.Status -eq 400) "got $($r.Status)"
$r = Invoke-Api POST "/api/orders" @{ shipping_address_id = $addrB.id } $a.Token @{ "Idempotency-Key" = (New-Key) }
Check "someone else's address -> 404" ($r.Status -eq 404) "got $($r.Status)"
$r = Invoke-Api POST "/api/orders" @{ shipping_address_id = $addrA.id; expected_total = 1.00 } $a.Token @{ "Idempotency-Key" = (New-Key) }
Check "stale expected_total -> 409, nothing ordered" ($r.Status -eq 409) "got $($r.Status)"
Check "cart untouched after the refusals" ((Invoke-Api GET "/api/cart" -Token $a.Token).Json.data.item_count -eq 2)

$key = New-Key
$r = Invoke-Api POST "/api/orders" @{ shipping_address_id = $addrA.id; expected_total = $cartTotal } $a.Token @{ "Idempotency-Key" = $key }
Check "place order -> 201" ($r.Status -eq 201) "got $($r.Status): $($r.Raw)"
$order = $r.Json.data
Write-Host "  order $($order.order_number): status=$($order.status) payment=$($order.payment_status) total=$($order.totals.total)"
Check "status pending / payment pending (never paid)" ($order.status -eq "pending" -and $order.payment_status -eq "pending")
Check "order total equals the cart total the customer saw" ([math]::Round($order.totals.total - $cartTotal, 2) -eq 0)
Check "order number looks like PRM-YYYY-NNNNNN" ($order.order_number -match '^PRM-\d{4}-\d{6,}$')
Check "item snapshot has name and quantity" ($order.items[0].product_name -eq $product.name -and $order.items[0].quantity -eq 2)
Check "shipping address snapshot copied" ($order.shipping_address.city -eq "Pune" -and $order.shipping_address.postal_code -eq "411001")
if ($couponApplied) { Check "coupon code recorded" ($order.coupon_code -eq $Coupon.ToUpper()) }
Check "response hides the idempotency key" (-not ($r.Raw -match [regex]::Escape($key)))
$cart = (Invoke-Api GET "/api/cart" -Token $a.Token).Json.data
Check "cart is empty after checkout" ($cart.item_count -eq 0 -and $null -eq $cart.coupon)

Section "5. Idempotency"
$r = Invoke-Api POST "/api/orders" @{ shipping_address_id = $addrA.id; expected_total = $cartTotal } $a.Token @{ "Idempotency-Key" = $key }
Check "same key, same body -> 200 with the same order" ($r.Status -eq 200 -and $r.Json.data.id -eq $order.id) "got $($r.Status)"
$r = Invoke-Api POST "/api/orders" @{ shipping_address_id = $addrA.id; expected_total = 1.00 } $a.Token @{ "Idempotency-Key" = $key }
Check "same key, different body -> 409" ($r.Status -eq 409) "got $($r.Status)"
$r = Invoke-Api GET "/api/orders?page_size=50" -Token $a.Token
Check "still exactly one order for user A" ($r.Json.data.pagination.total -eq 1)

Section "6. Empty cart"
$r = Invoke-Api POST "/api/orders" @{ shipping_address_id = $addrA.id } $a.Token @{ "Idempotency-Key" = (New-Key) }
Check "checkout with an empty cart -> 400" ($r.Status -eq 400) "got $($r.Status)"

Section "7. History and ownership"
$r = Invoke-Api GET "/api/orders" -Token $a.Token
Check "history lists the order" ($r.Status -eq 200 -and $r.Json.data.orders[0].id -eq $order.id)
Check "history row has total and item names" ($r.Json.data.orders[0].item_names -contains $product.name)
$r = Invoke-Api GET "/api/orders/$($order.id)" -Token $a.Token
Check "detail -> 200" ($r.Status -eq 200 -and $r.Json.data.id -eq $order.id)
$r = Invoke-Api GET "/api/orders/$($order.id)" -Token $b.Token
Check "user B cannot read user A's order -> 404" ($r.Status -eq 404) "got $($r.Status)"
$r = Invoke-Api GET "/api/orders" -Token $b.Token
Check "user B's history is empty" ($r.Json.data.pagination.total -eq 0)
$r = Invoke-Api POST "/api/orders/$($order.id)/cancel" $null $b.Token
Check "user B cannot cancel user A's order -> 404" ($r.Status -eq 404) "got $($r.Status)"
$r = Invoke-Api GET "/api/orders?page=0" -Token $a.Token
Check "page=0 -> 422" ($r.Status -eq 422) "got $($r.Status)"

Section "8. Cancel (releases stock, restores the coupon use)"
Write-Host "  (before cancelling you can look at the reserved stock - see the SQL hints at the end)"
$r = Invoke-Api POST "/api/orders/$($order.id)/cancel" $null $a.Token
Check "cancel -> 200, status cancelled" ($r.Status -eq 200 -and $r.Json.data.status -eq "cancelled") "got $($r.Status): $($r.Raw)"
Check "cancelled order is no longer cancellable" ($r.Json.data.can_cancel -eq $false -and $null -ne $r.Json.data.cancelled_at)
$r = Invoke-Api POST "/api/orders/$($order.id)/cancel" $null $a.Token
Check "cancelling again is safe -> 200, still cancelled" ($r.Status -eq 200 -and $r.Json.data.status -eq "cancelled")

Section "Summary"
Write-Host "  passed: $script:passed   failed: $script:failed"
Write-Host @"

Optional database checks (stock and coupon counters). PowerShell, from anywhere:

  docker exec -it healthy-harvest-postgres psql -U healthy_harvest -d healthy_harvest_db -c "select p.name, i.quantity, i.reserved_quantity from inventory i join products p on p.id = i.product_id where p.id = '$($product.id)';"
  docker exec -it healthy-harvest-postgres psql -U healthy_harvest -d healthy_harvest_db -c "select code, used_count, usage_limit from coupons where code = '$Coupon';"
  docker exec -it healthy-harvest-postgres psql -U healthy_harvest -d healthy_harvest_db -c "select order_number, status, payment_status, inventory_state, total_amount from orders where id = '$($order.id)';"

After the cancel, reserved_quantity should be back to what it was before this script ran, and the
coupon's used_count back down by one. The order should show cancelled / pending / released.
"@
if ($script:failed -gt 0) { exit 1 } else { exit 0 }