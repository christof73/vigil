"""
Allow running as: python -m vectis_intel
"""

from .server import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
