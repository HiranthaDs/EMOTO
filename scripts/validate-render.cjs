const fs = require('node:fs')
const yaml = require('../frontend/node_modules/js-yaml')
const Ajv = require('../frontend/node_modules/ajv/dist/2020').default

async function main() {
  const schema = await (await fetch('https://render.com/schema/render.yaml.json')).json()
  const blueprint = yaml.load(fs.readFileSync('render.yaml', 'utf8'))
  const ajv = new Ajv({ strict: false, allErrors: true, validateFormats: false })
  const valid = ajv.validate(schema, blueprint)
  console.log(JSON.stringify({ valid, errors: ajv.errors }, null, 2))
  process.exitCode = valid ? 0 : 1
}

main().catch(error => { console.error(error); process.exitCode = 1 })
