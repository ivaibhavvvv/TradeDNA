import urllib.request

routes = [
    "/",
    "/login",
    "/register",
    "/onboarding",
    "/dashboard/overview",
    "/dashboard/connections",
    "/dashboard/trades",
    "/dashboard/performance",
    "/dashboard/risk",
    "/dashboard/behavior",
    "/dashboard/trading-dna",
    "/dashboard/instruments",
    "/dashboard/sessions",
    "/dashboard/calendar",
    "/dashboard/operations",
    "/dashboard/recovery",
    "/dashboard/security",
    "/api/v1/health",
]

print("Testing all routes...")
all_ok = True
for r in routes:
    url = f"http://localhost:3000{r}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as res:
            print(f"  [200 OK] {r}")
    except Exception as e:
        print(f"  [FAIL] {r}: {e}")
        all_ok = False

if all_ok:
    print("\nALL 18 ROUTES VERIFIED SUCCESSFULLY WITH ZERO 404 ERRORS!")
else:
    print("\nSome routes failed.")
