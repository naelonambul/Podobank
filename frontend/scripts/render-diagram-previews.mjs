import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptDirectory, '../..');
const architectureDirectory = path.join(repositoryRoot, 'docs', 'architecture');

const diagrams = [
  {
    name: 'MariaDB ERD',
    source: path.join(architectureDirectory, 'podobank-current-erd.html'),
    output: path.join(architectureDirectory, 'podobank-current-erd.png'),
    viewport: { width: 1800, height: 1200 },
    screenshotStyle: `
      .page { width: 1760px !important; max-width: none !important; }
      .diagram-viewport { max-height: none !important; overflow: visible !important; }
    `,
  },
  {
    name: 'System architecture',
    source: path.join(architectureDirectory, 'podobank-current-architecture.html'),
    output: path.join(architectureDirectory, 'podobank-current-architecture.png'),
    viewport: { width: 2320, height: 1200 },
    screenshotStyle: `
      .page { width: 2280px !important; max-width: none !important; }
      .diagram-card, .diagram-scroll { overflow: visible !important; }
      .architecture { width: 2200px !important; min-width: 2200px !important; }
    `,
  },
];

async function renderPreviews() {
  await mkdir(architectureDirectory, { recursive: true });
  const browser = await chromium.launch({ headless: true });

  try {
    for (const diagram of diagrams) {
      const page = await browser.newPage({
        viewport: diagram.viewport,
        deviceScaleFactor: 2,
      });

      await page.goto(pathToFileURL(diagram.source).href, { waitUntil: 'load' });
      await page.evaluate(async () => {
        await globalThis.document.fonts.ready;
      });
      await page.addStyleTag({ content: diagram.screenshotStyle });
      await page.screenshot({
        path: diagram.output,
        fullPage: true,
        animations: 'disabled',
      });

      process.stdout.write(`${diagram.name}: ${path.relative(repositoryRoot, diagram.output)}\n`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
}

renderPreviews().catch((error) => {
  process.stderr.write(`Could not render diagram previews: ${error}\n`);
  process.exitCode = 1;
});
