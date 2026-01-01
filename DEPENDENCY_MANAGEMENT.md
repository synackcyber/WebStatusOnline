# Dependency Management Guide

## Overview

This project uses **pinned dependencies** (exact versions with `==`) instead of minimum version specifiers (`>=`) to ensure:

1. **Reproducible builds** - Same versions install every time
2. **Security** - Known, tested versions without unexpected updates
3. **Stability** - Prevents breaking changes from automatic updates
4. **Compliance** - Easier to audit and track vulnerabilities

## Files

- **`requirements.txt`** - Production dependencies (pinned versions)
- **`requirements-dev.txt`** - Development/testing dependencies
- **`requirements-lock.txt`** - Full dependency tree (auto-generated)

## Installation

### Production
```bash
pip install -r requirements.txt
```

### Development
```bash
pip install -r requirements.txt -r requirements-dev.txt
```

## Updating Dependencies

### 1. Check for outdated packages
```bash
pip list --outdated
```

### 2. Review security advisories
```bash
pip install safety
safety check --json
```

### 3. Update specific package
```bash
# Test the update first
pip install --upgrade package_name==new_version

# Run tests
pytest

# If tests pass, update requirements.txt
```

### 4. Update all dependencies (carefully)
```bash
# Create a test environment
python -m venv test_env
source test_env/bin/activate  # or test_env\Scripts\activate on Windows

# Install updated versions
pip install --upgrade -r requirements.txt

# Generate new pinned versions
pip freeze > requirements-new.txt

# Review changes
diff requirements.txt requirements-new.txt

# Run full test suite
pytest

# If tests pass, replace requirements.txt
mv requirements-new.txt requirements.txt
```

## Critical Security Updates

The following packages were updated for critical security vulnerabilities:

### certifi (2022.12.7 → 2024.12.14)
**CRITICAL**: Old version had outdated CA certificates, could allow MITM attacks
- CVE-2023-37920: TrustCor root certificates removed
- CVE-2022-23491: e-Tugra root certificate removed

### cryptography (41.0.3 → 44.0.0)
**HIGH**: Multiple security vulnerabilities in older versions
- CVE-2023-50782: Bleichenbacher vulnerability in RSA decryption
- CVE-2024-26130: NULL pointer dereference in PKCS12 parsing
- CVE-2024-0727: Denial of service in certificate verification

### fastapi (0.103.2 → 0.115.6)
**MEDIUM**: Security and stability improvements
- Improved OpenAPI security handling
- Better input validation
- Pydantic 2.x compatibility fixes

### httpx (0.24.1 → 0.28.1)
**MEDIUM**: HTTP/2 security fixes and connection handling
- Improved timeout handling
- Better error handling for malformed responses
- HTTP/2 connection reuse fixes

### uvicorn (0.22.0 → 0.34.0)
**MEDIUM**: WebSocket and connection handling improvements
- Better WebSocket security
- Improved signal handling
- Memory leak fixes

## Version Pinning Strategy

### Direct Dependencies
- **Exact pins** (`package==1.2.3`) for all direct dependencies
- Comments explain why each version is chosen
- Security-related updates noted

### Transitive Dependencies
- Let pip resolve automatically based on direct pins
- Monitor with `pip list` and `safety check`
- Pin if causing issues or security vulnerabilities

## Compatibility Notes

### Python Version
- Minimum: Python 3.8
- Recommended: Python 3.11+
- Tested: Python 3.8, 3.9, 3.10, 3.11, 3.12

### FastAPI + Pydantic
- FastAPI 0.115.x requires Pydantic 2.x
- Breaking changes from Pydantic 1.x to 2.x
- All models updated to Pydantic 2.x syntax

### Starlette
- Must match FastAPI's Starlette version requirement
- FastAPI 0.115.6 requires Starlette 0.41.x

## Security Scanning

### Automated scanning (CI/CD)
```bash
# Check for known vulnerabilities
safety check --json

# Security linting
bandit -r . -f json
```

### Manual review
1. Check GitHub Security Advisories
2. Review changelogs for security fixes
3. Test in staging environment first
4. Monitor application logs after updates

## Rollback Procedure

If an update causes issues:

```bash
# 1. Identify the problematic version
git diff requirements.txt

# 2. Revert to previous version
git checkout HEAD~1 requirements.txt

# 3. Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# 4. Verify application works
pytest
```

## Monitoring

### Regular checks (recommended schedule)

- **Daily**: Automated security scanning in CI/CD
- **Weekly**: Review `pip list --outdated`
- **Monthly**: Manual security advisory review
- **Quarterly**: Full dependency update cycle

### Tools

- **safety**: `pip install safety && safety check`
- **pip-audit**: `pip install pip-audit && pip-audit`
- **Dependabot**: Enable on GitHub for automatic PRs
- **Snyk**: For comprehensive vulnerability scanning

## Best Practices

1. ✅ **Always pin to exact versions** in production
2. ✅ **Test updates in staging first**
3. ✅ **Review changelogs before updating**
4. ✅ **Keep security packages updated** (cryptography, certifi)
5. ✅ **Document why specific versions are chosen**
6. ✅ **Run security scans regularly**
7. ❌ **Never use `>=` or `~=` in production**
8. ❌ **Never auto-update without testing**
9. ❌ **Never ignore security advisories**

## Emergency Security Update Process

If a critical vulnerability is discovered:

1. **Assess Impact**
   ```bash
   safety check --full-report
   ```

2. **Update Immediately**
   ```bash
   pip install --upgrade vulnerable-package==safe-version
   ```

3. **Test Critical Paths**
   ```bash
   pytest tests/test_security.py
   pytest tests/test_critical_functionality.py
   ```

4. **Deploy ASAP**
   - Skip normal staging window if critical
   - Monitor logs closely
   - Have rollback plan ready

5. **Update Requirements**
   ```bash
   pip freeze > requirements.txt
   git commit -m "SECURITY: Update vulnerable-package to safe-version"
   ```

## Support

For questions or issues with dependencies:
- Check package documentation
- Review GitHub issues for known problems
- Test updates in isolated virtual environment
- Consult security advisories before updating
