# Impact assessment: Project Alpha

| Field | Value |
|---|---|
| Version | 2 |
| Classification | internal |

## 3 Requirements

### 3.1 Functional

| ID | Requirement | Priority |
|---|---|---|
| REQ-001 | Users sign in with single sign-on through the corporate identity provider | High |
| REQ-002 | Nightly export of ledger balances to the reporting warehouse | High |
| FR-3 | Audit records retained for seven years in immutable storage | Medium |

### 3.2 Reporting

- NFR-1: Dashboard pages load within two seconds at peak volume.

### 3.3 Operations

| # | Requirement | GDS section |
|---|---|---|
| 1 | Operators receive alerting when replication lag exceeds thresholds | 6.1 |
| 2 | Quarterly certificate rotation runbook for the message broker cluster | |

### 3.4 Other

- NFR-2: Encrypted backups replicated to the secondary region daily.
- REQ-004: Purge customer mailing preferences after account closure.
