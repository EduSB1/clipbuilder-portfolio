import os

import httpx

from app.auth.clerk_store import get_or_sync_user_from_clerk

secret = os.getenv("CLERK_SECRET_KEY", "")
if not secret:
    print("ERRO: CLERK_SECRET_KEY nao encontrada")
    raise SystemExit(1)

headers = {"Authorization": f"Bearer {secret}"}
offset = 0
total = 0

with httpx.Client(timeout=30.0) as client:
    while True:
        resp = client.get(
            "https://api.clerk.com/v1/users",
            headers=headers,
            params={"limit": 100, "offset": offset},
        )
        resp.raise_for_status()
        users = resp.json()
        if not users:
            break

        for u in users:
            emails = u.get("email_addresses", [])
            primary_id = u.get("primary_email_address_id", "")
            email = ""
            if primary_id:
                email = next(
                    (e.get("email_address") for e in emails if e.get("id") == primary_id),
                    "",
                )
            if not email and emails:
                email = emails[0].get("email_address") or ""

            name = f"{u.get('first_name') or ''} {u.get('last_name') or ''}".strip()
            result = get_or_sync_user_from_clerk(u.get("id", ""), {"email": email, "full_name": name})
            status = "OK" if result else "FALHOU"
            print(f"{status} | {email}")
            total += 1

        if len(users) < 100:
            break
        offset += 100

print(f"\nTotal processados: {total}")
