#!/usr/bin/env python3
"""Generate access tokens for all hospitals in the database."""

import os
import sys
import secrets

# Add backend to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.database import get_db
from app.models.hospital import Hospital

def main():
    db = next(get_db())
    try:
        hospitals = db.query(Hospital).all()
        updated = 0
        
        for hospital in hospitals:
            if not hospital.access_token:
                hospital.access_token = secrets.token_urlsafe(32)
                updated += 1
                print(f"Generated token for {hospital.name} ({hospital.id}): {hospital.access_token}")
        
        if updated > 0:
            db.commit()
            print(f"\nUpdated {updated} hospitals with access tokens.")
        else:
            print("All hospitals already have access tokens.")
            
    finally:
        db.close()

if __name__ == "__main__":
    main()