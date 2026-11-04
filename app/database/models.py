"""Database Models and Schema Contracts.

SAFETY ARCHITECTURE NOTICE:
This service does NOT define or alter authoritative product, stock, or billing
tables. In accordance with Section 5 and Section 18 of the specification:
1. Authoritative product catalog belongs to the Main ShopFlow PostgreSQL database.
2. Voice AI acts as an interpretation microservice.
3. If persistent store for local alias cache is ever enabled in the future,
   it must follow this documented contract:

Future Optional Table: voice_custom_aliases
- tenant_id (VARCHAR(64), NOT NULL)
- alias_phrase (VARCHAR(255), NOT NULL)
- canonical_product_id (VARCHAR(64), NOT NULL)
- created_at (TIMESTAMP WITH TIME ZONE)
Primary Key: (tenant_id, alias_phrase)
Index: (tenant_id)
"""

from typing import Optional
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# No authoritative tables created here to prevent database divergence or destructive schema collisions.

