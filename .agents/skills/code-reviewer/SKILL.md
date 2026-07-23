---
name: code-reviewer
description: Standards for code reviews, code quality enforcement, anti-pattern detection, and zero-breaking-change refactoring.
---

# Code Review & Quality Standards

Use this skill when auditing codebase changes, refactoring modules, or performing automated code reviews for Python, HTML/CSS, and SQL.

## Verification & Safety Rules

1. **Zero Breaking Changes & Contract Integrity**
   - Ensure modifications to function signatures or API endpoints update all callers across the entire codebase.
   - Do not remove or alter existing database schema columns without backwards-compatible migration steps.
   - Validate that changes pass existing automated test suites (`pytest`).

2. **Error Prevention & Edge Cases**
   - Verify non-null checks (`if obj is not None:`) before property dereferencing to prevent `AttributeError`, `KeyError`, or `TypeError`.
   - Never swallow exceptions blindly with empty `except:` blocks or returning silent fallback values without logging the failure traceback.
   - Ensure proper cleanup of resources (file handles, database connections, HTTP sessions) using `async with` or `try ... finally`.

3. **Code Cleanliness & Maintainability**
   - Enforce explicit type hints for function arguments and return types.
   - Keep functions focused on a single responsibility (SRP). Split overly long methods (>50 lines) into smaller, testable helper functions.
   - Preserve existing docstrings, code comments, and logging formatting unless explicit changes are required.

4. **Testing & Verification Requirement**
   - Every bugfix or new feature must be verified with automated unit tests or execution scripts before concluding tasks.
