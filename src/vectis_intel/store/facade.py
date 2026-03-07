"""
Vectis Market Intelligence — Storage Facade
============================================
High-level facade over the entire storage layer.
"""

from .db import IntelDB
from .integrity import IntegrityEngine
from .repos import SourceRepo, SignalRepo, CorrelationRepo, OpportunityRepo, VerificationRepo
from .evidence import EvidenceChain


class IntelStore:
    """
    High-level facade over the entire storage layer.

    Usage:
        with IntelStore("vectis_intel.db") as store:
            source = store.sources.create(Source(...))
            signal = store.signals.create(Signal(...), [SignalSource(...)])
            chain = store.evidence.trace_signal(signal.signal_id)
            audit = store.integrity.run_integrity_audit()
    """

    def __init__(self, db_path: str = "vectis_intel.db"):
        self.db = IntelDB(db_path)
        self.integrity = IntegrityEngine(self.db.conn)
        self.sources = SourceRepo(self.db.conn)
        self.signals = SignalRepo(self.db.conn, self.integrity)
        self.correlations = CorrelationRepo(self.db.conn, self.integrity)
        self.opportunities = OpportunityRepo(self.db.conn, self.integrity)
        self.verifications = VerificationRepo(self.db.conn)
        self.evidence = EvidenceChain(self.db.conn)

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
