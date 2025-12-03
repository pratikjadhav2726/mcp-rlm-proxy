# Contributing to MCP Proxy Server

Thank you for your interest in contributing to MCP Proxy Server! This document provides guidelines and instructions for contributing.

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Respect different viewpoints and experiences

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in the [Issues](https://github.com/yourusername/mcp-proxy-server/issues)
2. If not, create a new issue with:
   - A clear, descriptive title
   - Steps to reproduce the bug
   - Expected vs actual behavior
   - Environment details (OS, Python version, etc.)
   - Relevant logs or error messages

### Suggesting Features

1. Check existing issues to see if the feature has been suggested
2. Create a new issue with:
   - A clear description of the feature
   - Use cases and examples
   - Potential implementation approach (if you have ideas)

### Submitting Pull Requests

1. **Fork the repository** and clone your fork
2. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

3. **Make your changes**:
   - Follow the existing code style
   - Add tests for new functionality
   - Update documentation as needed
   - Ensure all tests pass

4. **Commit your changes**:
   ```bash
   git commit -m "Add: description of your changes"
   ```
   Use clear, descriptive commit messages following [Conventional Commits](https://www.conventionalcommits.org/)

5. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create a Pull Request**:
   - Provide a clear description of your changes
   - Reference any related issues
   - Wait for review and address feedback

## Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/mcp-proxy-server.git
   cd mcp-proxy-server
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Install development dependencies**:
   ```bash
   uv sync --group dev
   ```

4. **Run tests**:
   ```bash
   uv run pytest
   ```

5. **Run linting** (if configured):
   ```bash
   uv run ruff check .
   ```

## Code Style

- Follow [PEP 8](https://pep8.org/) Python style guide
- Use type hints where appropriate
- Write docstrings for all public functions and classes
- Keep functions focused and single-purpose
- Use meaningful variable and function names

## Testing

- Write tests for new features
- Ensure all existing tests pass
- Aim for good test coverage
- Test edge cases and error conditions

## Documentation

- Update README.md if you add new features
- Add docstrings to new functions/classes
- Update examples if behavior changes
- Keep CHANGELOG.md updated

## Project Structure

```
mcp-proxy-server/
├── src/
│   └── mcp_proxy/          # Main package code
│       ├── __init__.py
│       ├── __main__.py     # Entry point
│       ├── server.py       # Main server implementation
│       ├── processors.py   # Projection and grep processors
│       └── config.py       # Configuration loading
├── tests/                  # Test files
├── examples/               # Example usage
├── docs/                   # Additional documentation
├── pyproject.toml          # Project configuration
└── README.md
```

## Questions?

Feel free to open an issue for questions or discussions. We're happy to help!

Thank you for contributing! 🎉

