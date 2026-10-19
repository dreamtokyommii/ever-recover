# 🔒 Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security issue, please report it responsibly.

### How to Report

**DO NOT** report security issues in public GitHub issues.

**DO** send a detailed report to: security@ever-recover.com

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Time

We aim to respond within 48 hours with:
- Acknowledgment of your report
- Initial assessment
- Timeline for fix

### Disclosure Policy

- We will notify you when the issue is fixed
- We request 90 days to patch before public disclosure
- You will be credited (with permission) in our security advisory

## Security Best Practices

### For Users

1. **Run as Non-Admin** - Avoid running as Administrator/root unless necessary
2. **Use Disk Images** - Always work on copies, not original evidence
3. **Verify Downloads** - Check file hashes before installation
4. **Keep Updated** - Install security patches promptly
5. **Scan Recovered Files** - Use antivirus on recovered data

### For Developers

1. **Input Validation** - Sanitize all user inputs
2. **Secure Dependencies** - Use signed, verified packages
3. **Code Review** - All changes require security review
4. **Test Coverage** - Include security-focused tests
5. **Static Analysis** - Run security scanners (bandit, safety)

## Security Features

### Built-in Protections

- **Sandboxed Execution** - File operations in controlled environment
- **Memory Safety** - No direct memory access, uses safe APIs
- **Input Validation** - All inputs sanitized before processing
- **Error Handling** - Graceful failures, no sensitive data in errors
- **Logging** - Audit trail for forensic analysis

### Dependencies

We regularly audit our dependencies:
- PyQt6 - GUI framework (verified)
- ReportLab - PDF generation (verified)
- NumPy - Numerical computing (verified)
- Tqdm - Progress bars (verified)

## Security Tools

We use:
- **Bandit** - Python security linter
- **Safety** - Dependency vulnerability checker
- **Snyk** - Automated security scanning
- **GitHub Dependabot** - Automatic security updates

## Acknowledgments

Security researchers who helped improve Ever Recover:
- (Your name here - report a vulnerability!)

---

**Last Updated:** July 2026