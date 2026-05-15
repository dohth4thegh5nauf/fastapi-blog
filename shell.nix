
{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    # Python environment
    python312
    
    # Project dependencies from pyproject.toml
    (python312.withPackages (ps: with ps; [
      fastapi
      jinja2
      jinja2_time
      markdown
      nh3
      pydantic
      pyyaml
      pymdownx
      uvicorn
      starlette_admin
      sqlalchemy
      aiosqlite
      itsdangerous
      pyjwt
      passlib
      bcrypt
      python_multipart
      redis
      hiredis
      # Dev dependencies
      httpx
      ruff
      pytest
      coverage
      mypy
      types_markdown
      types_pyyaml
      # Additional dependencies for extras
      babel # for starlette-admin[i18n]
      greenlet # for sqlalchemy[asyncio]
    ]))
    
    # Other tools
    curl
  ];

  shellHook = ''
    echo "Nix-shell environment for fastapi-blog is ready."
    echo "Run './demo.sh roles' to start the application."
  '';
}
