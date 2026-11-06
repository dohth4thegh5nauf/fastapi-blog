import { createAjvValidator, createJSONEditor } from '../vendor/vanilla-jsoneditor-3.13.0.js'

for (const target of document.querySelectorAll('.field-role-permissions-json')) {
  const input = document.querySelector(`input[name="${CSS.escape(target.id)}"]`)
  if (!input) {
    continue
  }

  let content
  try {
    content = { json: JSON.parse(input.value || '{}') }
  } catch {
    content = { text: input.value }
  }

  const schema = JSON.parse(target.dataset.validationSchema || '{}')
  const updateTheme = () => {
    target.classList.toggle(
      'jse-theme-dark',
      document.documentElement.dataset.bsTheme === 'dark',
    )
  }

  updateTheme()
  new MutationObserver(updateTheme).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-bs-theme'],
  })

  createJSONEditor({
    target,
    props: {
      content,
      ariaLabel: target.getAttribute('aria-label'),
      validator: createAjvValidator({ schema }),
      mode: 'tree',
      onChange(updatedContent) {
        input.value = 'json' in updatedContent
          ? JSON.stringify(updatedContent.json)
          : updatedContent.text
      },
    },
  })
}
