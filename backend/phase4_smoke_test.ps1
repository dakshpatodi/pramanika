$base = "http://localhost:8000"

Write-Host "`n=== 1. Basic listing ===" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/products"
Write-Host "Total: $($r.data.pagination.total), Page: $($r.data.pagination.page), Products returned: $($r.data.products.Count)"

Write-Host "`n=== 2. Pagination (page_size=3) ===" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/products?page=1&page_size=3"
Write-Host "page_size=3 -> returned $($r.data.products.Count), total_pages=$($r.data.pagination.total_pages), has_next=$($r.data.pagination.has_next)"

Write-Host "`n=== 3. Search ===" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/products?search=poha"
Write-Host "search=poha -> $($r.data.products.Count) result(s): $($r.data.products.name -join ', ')"

Write-Host "`n=== 4. Category filtering ===" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/products?category=dry-fruits"
Write-Host "category=dry-fruits -> $($r.data.products.Count) result(s): $($r.data.products.name -join ', ')"

Write-Host "`n=== 5. Price filtering ===" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/products?min_price=200&max_price=500"
Write-Host "200-500 -> $($r.data.products.Count) result(s), prices: $($r.data.products.price -join ', ')"

Write-Host "`n=== 6. Availability (in_stock/low_stock flags visible) ===" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/products?page_size=20"
$r.data.products | ForEach-Object { Write-Host "$($_.name): in_stock=$($_.in_stock), low_stock=$($_.low_stock)" }

Write-Host "`n=== 7. Sorting (price_asc) ===" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/products?sort=price_asc&page_size=20"
Write-Host ($r.data.products | ForEach-Object { "$($_.name)=$($_.price)" }) -join " -> "

Write-Host "`n=== 8. Combined filters ===" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/products?category=ready-mixes&min_price=100&max_price=200&sort=name_asc&page=1"
Write-Host "combined -> $($r.data.products.Count) result(s): $($r.data.products.name -join ', ')"

Write-Host "`n=== 9. Product detail (with related_products) ===" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/products/multigrain-cereal"
Write-Host "Name: $($r.data.name), Price: $($r.data.price), Related: $($r.data.related_products.name -join ', ')"

Write-Host "`n=== 10. Product not found -> 404 ===" -ForegroundColor Cyan
try { Invoke-RestMethod -Uri "$base/api/products/does-not-exist" }
catch { Write-Host "$($_.Exception.Response.StatusCode.value__): $($_.ErrorDetails.Message)" }

Write-Host "`n=== 11. Categories list (with product_count) ===" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/categories"
$r.data | ForEach-Object { Write-Host "$($_.name): $($_.product_count) products" }

Write-Host "`n=== 11b. Category detail + unknown category -> 404 ===" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/categories/cereals"
Write-Host "Found: $($r.data.name)"
try { Invoke-RestMethod -Uri "$base/api/categories/does-not-exist" }
catch { Write-Host "$($_.Exception.Response.StatusCode.value__): $($_.ErrorDetails.Message)" }

Write-Host "`n=== 12. Unmatched category FILTER on listing -> 200 with empty list (not 404) ===" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri "$base/api/products?category=does-not-exist"
Write-Host "Products returned: $($r.data.products.Count), total: $($r.data.pagination.total)"

Write-Host "`n=== 13. Invalid parameters -> all should be 422 ===" -ForegroundColor Cyan
$invalidCases = @(
    "$base/api/products?page=0",
    "$base/api/products?page_size=500",
    "$base/api/products?sort=totally_invalid",
    "$base/api/products?min_price=500&max_price=100"
)
foreach ($url in $invalidCases) {
    try { Invoke-RestMethod -Uri $url }
    catch { Write-Host "$url -> $($_.Exception.Response.StatusCode.value__): $($_.ErrorDetails.Message)" }
}

Write-Host "`n=== Done ===" -ForegroundColor Green
