"""Tests for the admin panel (list, forms, dashboard) with a custom schema."""

import asyncio
import datetime
import pathlib
import re
import warnings
from types import SimpleNamespace

import jinja2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog
import fastapi_blog.admin as fastapi_blog_admin
from fastapi_blog import DEFAULT_SCHEMA, FieldSpec, FrontmatterSchema, helpers
from fastapi_blog.admin.form_fields import build_form_fields, form_fields_meta
from fastapi_blog.admin.markdown_crud import (
  MarkdownCreateView,
  MarkdownEditView,
  MarkdownFileManager,
  MarkdownListView,
  MarkdownPost,
  get_posts_directory,
)
from fastapi_blog.admin.views import load_posts_for_home
from fastapi_blog.config import CollectionSpec
from fastapi_blog.templates import (
  SLUG_TAGS_DEFAULT,
  SUMMARY_TAGS,
  parse_template,
)


ADMIN_TEMPLATES = (
  pathlib.Path(fastapi_blog.__file__).parent / 'admin' / 'templates'
)

EXTERNAL_SCHEMA = FrontmatterSchema(
  fields=(
    FieldSpec('headline', alias='title', required=True, role='title'),
    FieldSpec(
      'pub_date', alias='pubDate', type='date', required=True, role='date'
    ),
    FieldSpec('is_public', alias='isPublic', type='bool', role='published'),
    FieldSpec('labels', type='list[str]', role='tags'),
    FieldSpec('summary', role='description'),
  ),
)


class FakeRequest:
  def __init__(self, **path_params):
    """Store path params the same way Starlette's Request does."""
    self.path_params = path_params
    self.scope = {'root_path': '/admin'}


class FakeTemplates:
  """Records what a view passes to the template instead of rendering it."""

  def TemplateResponse(self, request, name, context, status_code=200):
    return {'name': name, 'context': context, 'status': status_code}


def render(view, **path_params):
  view.templates = FakeTemplates()
  return asyncio.run(view.index(FakeRequest(**path_params)))


@pytest.fixture
def posts_dir(tmp_path):
  (tmp_path / 'a.md').write_text(
    '---\ntitle: Alpha\npubDate: 2024-01-01\nisPublic: true\n'
    'labels: [x, y]\n---\n\nBody A\n'
  )
  (tmp_path / 'b.md').write_text(
    '---\ntitle: Beta\npubDate: 2024-03-01\nisPublic: false\n---\n\nBody B\n'
  )
  (tmp_path / 'c.md').write_text('---\nfoo: 1\n---\n\nNo role values\n')
  return str(tmp_path)


# --- MarkdownPost and the file manager ---------------------------------------


def test_markdown_post_default_schema_is_unchanged():
  post = MarkdownPost(
    's', {'title': 'T', 'date': '2024', 'published': True, 'tags': ['a']}, 'c'
  )
  assert (post.title, post.date, post.published, post.tags) == (
    'T',
    '2024',
    True,
    ['a'],
  )
  empty = MarkdownPost('s', {}, 'c')
  assert empty.title == 's'
  assert empty.date == ''
  assert empty.published is False
  assert empty.tags == []


def test_markdown_post_reads_values_by_role():
  frontmatter = {
    'title': 'T',
    'pubDate': '2024-01-01',
    'isPublic': True,
    'labels': ['a'],
  }
  post = MarkdownPost('s', frontmatter, 'c', EXTERNAL_SCHEMA)
  assert post.title == 'T'
  assert str(post.date) == '2024-01-01'
  assert post.published is True
  assert post.tags == ['a']


def test_file_manager_sorts_by_the_date_role(posts_dir):
  manager = MarkdownFileManager(posts_dir, EXTERNAL_SCHEMA)
  assert [p.slug for p in manager.list_posts()] == ['b', 'a', 'c']
  assert manager.load_post('a').title == 'Alpha'
  assert manager.load_post('c').title == 'c'  # no title: the slug


# --- Views --------------------------------------------------------------------


def test_list_view_shows_the_columns_of_bound_roles(posts_dir):
  result = render(MarkdownListView(posts_dir, 'en', EXTERNAL_SCHEMA))
  context = result['context']
  assert context['columns'] == {'date': True, 'published': True, 'tags': True}
  assert [p['slug'] for p in context['posts']] == ['b', 'a', 'c']
  assert context['posts'][1]['tags'] == 'x, y'

  minimal = FrontmatterSchema(fields=(FieldSpec('title', role='title'),))
  columns = render(MarkdownListView(posts_dir, 'en', minimal))['context'][
    'columns'
  ]
  assert columns == {'date': False, 'published': False, 'tags': False}


def test_list_view_renders_collection_summary(posts_dir):
  spec = CollectionSpec(
    name='posts',
    dir=posts_dir,
    schema=EXTERNAL_SCHEMA,
    summary=parse_template(
      '{headline} — {labels}',
      SUMMARY_TAGS,
      {field.name for field in EXTERNAL_SCHEMA.fields},
    ),
  )
  result = render(
    MarkdownListView(posts_dir, 'en', EXTERNAL_SCHEMA, collection_spec=spec)
  )
  posts = {post['slug']: post for post in result['context']['posts']}
  assert posts['a']['summary'] == "Alpha — ['x', 'y']"
  assert posts['b']['summary'] == 'Beta — '


def test_create_view_exposes_generated_slug_option(posts_dir):
  spec = CollectionSpec(
    name='posts',
    dir=posts_dir,
    schema=EXTERNAL_SCHEMA,
    slug_template=parse_template(
      '{seq|pad(4)}-{title_slug}',
      SLUG_TAGS_DEFAULT,
      {field.name for field in EXTERNAL_SCHEMA.fields},
    ),
  )
  context = render(
    MarkdownCreateView(posts_dir, 'en', EXTERNAL_SCHEMA, collection_spec=spec)
  )['context']
  assert context['auto_slug'] is True


def test_list_view_without_schema_shows_all_columns(posts_dir):
  columns = render(MarkdownListView(posts_dir, 'en'))['context']['columns']
  assert columns == {'date': True, 'published': True, 'tags': True}


def test_edit_view_builds_the_form_from_the_schema(posts_dir):
  result = render(MarkdownEditView(posts_dir, 'en', EXTERNAL_SCHEMA), slug='a')
  context = result['context']
  fields = {f['name']: f for f in context['form_fields']}
  assert fields['headline']['value'] == 'Alpha'
  assert fields['pub_date']['value'] == '2024-01-01'
  assert fields['is_public']['value'] == 'true'
  assert fields['labels']['value'] == 'x, y'
  assert context['post']['content'] == 'Body A'
  assert context['form_fields_meta'][1] == {
    'name': 'pub_date',
    'key': 'pubDate',
    'kind': 'date',
  }
  assert 'Alpha' in context['title']


def test_edit_view_post_not_found(posts_dir):
  view = MarkdownEditView(posts_dir, 'en', EXTERNAL_SCHEMA)
  assert render(view, slug='missing')['status'] == 404


def test_create_view_starts_with_initial_values(posts_dir):
  result = render(MarkdownCreateView(posts_dir, 'en', EXTERNAL_SCHEMA))
  context = result['context']
  fields = {f['name']: f for f in context['form_fields']}
  assert context['is_new'] is True
  assert fields['pub_date']['value'] == datetime.date.today().isoformat()
  assert fields['is_public']['value'] == 'false'


def test_create_view_without_schema_has_the_builtin_fields(posts_dir):
  context = render(MarkdownCreateView(posts_dir, 'en'))['context']
  names = [f['name'] for f in context['form_fields']]
  assert names == ['title', 'date', 'published', 'tags', 'description']


# --- Templates ----------------------------------------------------------------


def _render_template(name, **context):
  layout = (
    '{% block head_css %}{% endblock %}{% block header %}{% endblock %}'
    '{% block content %}{% endblock %}'
  )
  loader = jinja2.ChoiceLoader(
    [
      jinja2.DictLoader({'layout.html': layout}),
      jinja2.FileSystemLoader(str(ADMIN_TEMPLATES)),
    ]
  )
  env = jinja2.Environment(loader=loader, autoescape=True)
  env.globals['url_for'] = lambda *args, **kwargs: '/url'
  env.globals['__name__'] = 'admin'
  return env.get_template(name).render(**context)


LABELS = {
  'title': 'Title',
  'date': 'Date',
  'published': 'Published',
  'tags': 'Tags',
  'description': 'Description',
  'tags_hint': 'Comma-separated tags',
}
FORM_T = {
  **LABELS,
  'posts': 'Posts',
  'admin': 'Admin',
  'create': 'Create',
  'edit_title': 'Edit',
  'slug': 'Slug',
  'slug_hint': '',
  'yes': 'Yes',
  'no': 'No',
  'content': 'Content',
  'content_hint': '',
  'cancel': 'Cancel',
  'save': 'Save',
}


def _edit_page(schema, frontmatter, is_new=False):
  fields = build_form_fields(schema, frontmatter, LABELS, is_new=is_new)
  html = _render_template(
    'markdown_edit.html',
    t=FORM_T,
    title='Edit',
    post={
      'slug': 's',
      'title': 'T',
      'content': 'c',
      'frontmatter': frontmatter,
    },
    form_fields=fields,
    form_fields_meta=form_fields_meta(fields),
    is_new=is_new,
  )
  return fields, html


def test_edit_template_renders_every_schema_field():
  fields, html = _edit_page(
    EXTERNAL_SCHEMA, {'title': 'T', 'pubDate': '2024-01-01'}
  )
  for field in fields:
    assert f'id="field-{field["name"]}"' in html
  assert 'type="date"' in html
  assert '<select class="form-select" id="field-is_public"' in html


def test_form_groups_seo_fields_and_shows_configured_counters():
  from fastapi_blog.models import SeoCheckConfig, SeoConfig

  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', role='title'),
      FieldSpec('summary', role='description'),
      FieldSpec('metadata', type='object', fields=(
        FieldSpec('source_url', type='link', alias='url'),
      )),
      FieldSpec('references', type='list[object]', fields=(
        FieldSpec('label'),
        FieldSpec('href', alias='url'),
      )),
    ),
    seo=SeoConfig(check=SeoCheckConfig(title_max=55, description_max=145)),
  )
  fields, html = _edit_page(
    schema,
    {
      'title': 'Example',
      'summary': 'Description',
      'metadata': {'url': 'https://example.org/source'},
      'references': [{'label': 'Reference', 'url': 'https://example.org/ref'}],
    },
  )
  by_name = {field['name']: field for field in fields}
  assert by_name['title']['group'] == 'SEO'
  assert by_name['title']['counter_max'] == 55
  assert by_name['summary']['group'] == 'SEO'
  assert by_name['summary']['counter_max'] == 145
  assert by_name['metadata__source_url']['path'] == ['metadata', 'url']
  assert by_name['references']['kind'] == 'json'
  assert 'SEO' in html
  assert 'data-counter-max="55"' in html
  assert 'data-counter-max="145"' in html
  assert 'field-references' in html


def test_edit_template_escapes_values():
  frontmatter = {'title': 'A "quoted" <b>', 'date': '2024-01-01'}
  _, html = _edit_page(DEFAULT_SCHEMA, frontmatter)
  assert 'value="A &#34;quoted&#34; &lt;b&gt;"' in html
  assert '<b>' not in html


def test_edit_template_passes_the_field_keys_to_the_script():
  fields, html = _edit_page(EXTERNAL_SCHEMA, {})
  match = re.search(r'const formFields = (\[.*?\]);', html, re.S)
  assert match is not None
  assert match.group(1).count('"key"') == len(fields)
  assert '"key": "title"' in match.group(1)
  assert '"key": "pubDate"' in match.group(1)


def test_edit_template_marks_required_fields_for_the_browser():
  _, html = _edit_page(DEFAULT_SCHEMA, {})
  assert re.search(r'id="field-title"[^>]*required', html)
  assert not re.search(r'id="field-description"[^>]*required', html)


def _list_page(posts, columns):
  names = (
    'posts admin new_post title slug date status tags actions published draft '
    'edit delete no_posts_found create_first_post delete_confirm error '
    'failed_to_delete'
  ).split()
  return _render_template(
    'markdown_list.html',
    t={name: name for name in names},
    posts=posts,
    columns=columns,
  )


def _header_count(html):
  return len(re.findall(r'<th[ >]', html))


def test_list_template_hides_columns_of_unbound_roles():
  posts = [
    {'slug': 'a', 'title': 'A', 'date': '2024', 'published': True, 'tags': 'x'}
  ]
  full = _list_page(posts, {'date': True, 'published': True, 'tags': True})
  minimal = _list_page(
    posts, {'date': False, 'published': False, 'tags': False}
  )
  assert _header_count(full) == 6
  assert _header_count(minimal) == 3
  assert 'badge' in full
  assert 'badge' not in minimal
  assert '<td class="text-muted">2024</td>' not in minimal


def test_list_template_empty_row_spans_all_columns():
  columns = {'date': True, 'published': False, 'tags': True}
  assert 'colspan="5"' in _list_page([], columns)


# --- Dashboard ----------------------------------------------------------------


def test_load_posts_for_home_uses_roles(posts_dir):
  posts = load_posts_for_home(posts_dir, EXTERNAL_SCHEMA)
  assert [p.slug for p in posts] == ['b', 'a', 'c']
  alpha = posts[1]
  assert isinstance(alpha.date, datetime.datetime)
  assert alpha.date.date() == datetime.date(2024, 1, 1)
  assert alpha.published is True
  assert alpha.tags == ['x', 'y']
  assert posts[2].date is None
  assert posts[2].tags == []


def test_load_posts_for_home_handles_string_dates(tmp_path):
  schema = FrontmatterSchema(fields=(FieldSpec('when', role='date'),))
  (tmp_path / 'iso.md').write_text(
    "---\nwhen: '2024-05-01T10:00:00'\n---\n\nx\n"
  )
  (tmp_path / 'bad.md').write_text('---\nwhen: soon\n---\n\nx\n')
  posts = {p.slug: p for p in load_posts_for_home(str(tmp_path), schema)}
  assert posts['iso'].date == datetime.datetime(2024, 5, 1, 10, 0)
  assert posts['bad'].date is None


def _home_page(date):
  post = SimpleNamespace(
    slug='s', title='My title', published=True, date=date, tags=[]
  )
  stats = {
    'total_posts': 1,
    'published_posts': 1,
    'draft_posts': 0,
    'total_tags': 0,
  }
  return _render_template(
    'home.html', t=SimpleNamespace(), posts=[post], stats=stats, top_tags=[]
  )


def test_home_template_shows_the_date_when_there_is_one():
  html = _home_page(datetime.datetime(2024, 5, 1, 10, 0))
  assert 'My title' in html
  assert 'May 01, 2024' in html


def test_home_template_tolerates_posts_without_a_date():
  html = _home_page(None)
  assert 'My title' in html
  assert '2024' not in html


# --- Wiring -------------------------------------------------------------------


@pytest.fixture
def workdir(tmp_path, monkeypatch):
  (tmp_path / 'posts').mkdir()
  (tmp_path / 'pages').mkdir()
  monkeypatch.chdir(tmp_path)
  helpers.list_posts.cache_clear()
  yield tmp_path
  helpers.list_posts.cache_clear()


def test_add_admin_to_app_accepts_a_schema(workdir):
  app = FastAPI()
  admins = fastapi_blog.add_admin_to_app(
    app,
    admin_username='admin',
    admin_password='Admin123!',
    secret_key='a' * 64,
    locales=['en'],
    default_locale='en',
    frontmatter_schema=EXTERNAL_SCHEMA,
  )
  assert 'en' in admins


def test_setup_fastapi_blog_applies_the_schema_everywhere(workdir):
  app = FastAPI()
  admins = fastapi_blog.setup_fastapi_blog(
    app,
    include_api=True,
    admin_username='admin',
    admin_password='Admin123!',
    secret_key='a' * 64,
    frontmatter_schema=EXTERNAL_SCHEMA,
  )
  assert 'en' in admins

  client = TestClient(app)
  payload = {
    'frontmatter': {
      'title': 'Hello',
      'pubDate': '2024-05-01',
      'isPublic': True,
    },
    'content': 'Body',
  }
  auth = ('admin', 'Admin123!')
  created = client.post('/api/posts/create/hello', json=payload, auth=auth)
  assert created.status_code == 201
  assert 'Hello' in client.get('/blog/posts').text


def test_setup_fastapi_blog_threads_posts_dirname_to_add_admin(monkeypatch):
  """`setup_fastapi_blog(posts_dirname=...)` must pass it on to `add_admin_to_app`.

  It used to be dropped: the admin panel read posts via
  `get_posts_directory()` alone (a `POSTS_DIR` env var or a cwd-based
  guess), so it could silently point at a different directory than
  `setup_fastapi_blog(posts_dirname=...)` configured for the blog/REST API.
  """
  captured = {}
  real_add_admin = fastapi_blog_admin.add_admin_to_app

  def spy(*args, **kwargs):
    captured.update(kwargs)
    return real_add_admin(*args, **kwargs)

  monkeypatch.setattr(fastapi_blog_admin, 'add_admin_to_app', spy)
  monkeypatch.setattr(fastapi_blog, '_import_admin', lambda: fastapi_blog_admin)

  fastapi_blog.setup_fastapi_blog(
    FastAPI(),
    posts_dirname='content',
    admin_username='admin',
    admin_password='Admin123!',
    secret_key='a' * 64,
  )
  assert captured['posts_dirname'] == 'content'


def test_admin_panel_reads_posts_from_posts_dirname(tmp_path, monkeypatch):
  """A post created via the REST API shows up on the admin Home page.

  End to end, when both are configured with the same explicit
  `posts_dirname`.
  """
  monkeypatch.chdir(tmp_path)
  monkeypatch.delenv('POSTS_DIR', raising=False)
  content_dir = tmp_path / 'content'
  content_dir.mkdir()
  helpers.list_posts.cache_clear()

  app = FastAPI()
  fastapi_blog_admin.add_admin_to_app(
    app,
    database_url='sqlite+aiosqlite:///:memory:',
    admin_username='admin',
    admin_password='Admin123!',
    secret_key='a' * 64,
    locales=['en'],
    default_locale='en',
    posts_dirname='content',
  )
  fastapi_blog.add_blog_to_fastapi(
    app,
    posts_dirname='content',
    include_api=True,
    admin_username='admin',
    admin_password='Admin123!',
  )

  with TestClient(app) as client:
    payload = {
      'frontmatter': {
        'title': 'In Content Dir',
        'date': '2024-05-01',
        'published': True,
      },
      'content': 'Body',
    }
    created = client.post(
      '/api/posts/create/hello', json=payload, auth=('admin', 'Admin123!')
    )
    assert created.status_code == 201
    assert (content_dir / 'hello.md').exists()

    login_page = client.get('/admin/login')
    token = re.search(
      r'name="csrftoken" value="([^"]+)"', login_page.text
    ).group(1)
    client.post(
      '/admin/login',
      data={
        'username': 'admin',
        'password': 'Admin123!',
        'csrftoken': token,
      },
    )
    home = client.get('/admin/')
    assert 'In Content Dir' in home.text

  helpers.list_posts.cache_clear()


def test_posts_dir_env_var_is_deprecated(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  monkeypatch.setenv('POSTS_DIR', str(tmp_path / 'env-posts'))
  with pytest.warns(DeprecationWarning, match='POSTS_DIR'):
    result = get_posts_directory()
  assert result == str(tmp_path / 'env-posts')


def test_posts_dirname_argument_skips_the_deprecation_warning(
  tmp_path, monkeypatch
):
  monkeypatch.setenv('POSTS_DIR', str(tmp_path / 'env-posts'))
  with warnings.catch_warnings():
    warnings.simplefilter('error')
    assert get_posts_directory('explicit-dir') == 'explicit-dir'


def test_hidden_and_read_only_object_parent_are_respected_in_admin_form():
  schema = FrontmatterSchema(fields=(
    FieldSpec('private', type='object', hidden=True, fields=(
      FieldSpec('value'),
    )),
    FieldSpec('locked', type='object', read_only=True, fields=(
      FieldSpec('identifier'),
      FieldSpec('label'),
    )),
  ))
  fields = build_form_fields(
    schema,
    {'private': {'value': 'secret'}, 'locked': {'identifier': 'id', 'label': 'A'}},
    {},
  )
  by_name = {field['name']: field for field in fields}
  assert by_name['private']['kind'] == 'hidden'
  assert by_name['locked__identifier']['read_only'] is True
  assert by_name['locked__label']['read_only'] is True
