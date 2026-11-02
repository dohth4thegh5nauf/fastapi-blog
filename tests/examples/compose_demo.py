"""Application served by the container image and the Compose stack.

Core only (no extras, no credentials): the blog plus the health probes
that the container/Compose health checks and CI integration smoke call.
Serves the shared example posts, which are written in the lenient
frontmatter format, so strict validation is turned off like in the other
example applications.
"""

from fastapi import FastAPI

import fastapi_blog


app = FastAPI(title='fastapi-blog demo')
app = fastapi_blog.add_blog_to_fastapi(
  app,
  locales=['en', 'ru'],
  default_locale='en',
  strict_frontmatter=False,
  health_routes=True,
)
