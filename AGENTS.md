# AI Instructions

Hello AI! 👋

Please, don’t modify this file!

## Rules

- Use Russian to communicate in the chat.
- Use English for comments in the code. For example:
  ```python
  # Good: Use contractions and apostrophes
  def process_data():
    # Don’t process if data isn’t valid
    if not is_valid:
      return None
  ```
- Use English for command output messages. For example:
  ```python
  def do_something():
    # Don’t print msg if `debug` isn’t equal True
    if debug:
      print('English is a West Germanic language of the Indo-European language family that emerged in early medieval England and has since become a global lingua franca.')
  ```
- We currently don’t support Windows or macOS. Only Ubuntu in the latest LTS version.
- Don’t use the word "folder" in comments and documentation, use "directory" or "catalog".
- Use the `./docs/` directory for documentation.
- Use the `./tmp/` directory for temporary files and one-time scripts.
- Use the `./log/` directory for logging.
- The `./+/` directory:
  - Isn’t related to the project in any way; it stores additional and reference materials.
  - Should be excluded from any CI checks; references to it and its contents cannot appear in code or documentation.
  - However, it shouldn’t be listed in `.gitignore`-file.

## Semantic versioning

- Use the `pyproject.toml` file to specify the current version number, using the following logic:
  - `MAJOR.x.x`: breaking changes;
  - `x.MINOR.x`: new functionality, backward compatibility;
  - `x.x.PATCH`: bug fixes;
  - `x.x.x.BUILD`: build number or ID (optionally as needed).

## Style

- Use two spaces for indentation (by default in all PL’s). For example:
  ```python
  def my_function():
    if condition:
      do_something()
  ```
- Use single quotes instead of double quotes where possible:
  ```python
  # Good (single quotes for regular strings)
  name = 'John'
  message = f'Hello, {name}!'
  ```
  Exceptions:
  1. For multiline strings (triple quotes), double quotes `"""` are always used, regardless of the quote-style setting (ruff). This is done for consistency with PEP 257 (docstring conventions).
    ```python
    # Multiline strings use triple double quotes (PEP 257). Enforced by Ruff formatter for docstring convention consistency
    script = f"""// Multi-line
    content here
    """
  
    def function():
      """Docstrings always use triple double quotes."""
      pass
    ```
  2. HTML tag attributes (by default in all PL’s)
    ```html
      <!DOCTYPE html>
      <html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Document</title>
      </head><body>
        <div class="container"></div>
      </body></html>
    ```
    ```python
    html = '<div class="container"></div>'  # HTML attributes use double quotes
    ```
    ```javascript
      function createElementFromHTML(htmlString) {
        const template = document.createElement('template');
        template.innerHTML = htmlString.trim();
        return template.content.firstElementChild;
      }
      const myElement = createElementFromHTML('<div class="card"><h1>Hello World</h1></div>'); // HTML attributes use double quotes
      document.body.appendChild(myElement);
    ```
- Use backticks (aka backquotes, grave accents) to highlight code, commands, paths, filenames, URI etc in comments, similar to how it is done in Markdown. For example:
  ```python
  # Run with `python agent.py`
  # Save to `data/documents.pdf`
  # Fetch from `https://api.example.com/data`
  ```
- Use a formula like `[link_text](link_URL)` to highlight named links in comments, similar to how it is used in Markdown. For example:
  ```python
  # See [documentation](https://docs.python.org) for details
  ```
- Use the `return` keyword in all functions that return values, and those values are used further.
