"""Application served by the container image and the Compose stack.

Core only (no extras, no credentials): the blog plus the health probes
that the container/Compose health checks and CI integration smoke call.
"""

from fastapi import FastAPI

import fastapi_blog


app = FastAPI(title='fastapi-blog demo')
app = fastapi_blog.add_blog_to_fastapi(
  app,
  locales=['en', 'ru'],
  default_locale='en',
  health_routes=True,
)
