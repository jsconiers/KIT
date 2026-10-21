# General design specification: Project Alpha

## 4 Identity

### 4.1 Authentication

Sign-in uses single sign-on (REQ-001).

## 5 Data

### 5.1 Export

A nightly batch export to the warehouse covers REQ-002 and FR-3. REQ-099 is a later addition.

### 5.2 Dashboards

Addresses IA 3.2: a caching layer keeps page loads fast.

## 6 Operations

### 6.1 Monitoring

Alert rules watch replication lag.

### 6.2 Backup

Backups are encrypted and replicated daily to the secondary region.
