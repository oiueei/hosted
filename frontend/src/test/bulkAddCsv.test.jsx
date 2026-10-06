import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, test, expect, beforeEach } from 'vitest';
import JSZip from 'jszip';

vi.mock('../services/api', () => ({ apiFetch: vi.fn() }));
// The ticketed upload path is covered in src/utils/uploadImage.test.js; here it
// only has to receive the right File and hand back a public_id.
// The real constants and error classes stay; only the upload is stubbed. `UPLOADS_PER_HOUR`
// reads through `allowance` so one test can lower it: the real one (120) is above the 100
// rows a file may hold, so with a cover photo per row it cannot be crossed.
const allowance = vi.hoisted(() => ({ perHour: null }));
vi.mock('../utils/uploadImage', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    uploadImage: vi.fn(),
    get UPLOADS_PER_HOUR() {
      return allowance.perHour ?? actual.UPLOADS_PER_HOUR;
    },
  };
});

import { apiFetch } from '../services/api';
import { uploadImage, UploadRateLimitedError } from '../utils/uploadImage';
import BulkAddCsv from '../components/BulkAddCsv';

const fileInput = (container) => container.querySelector('input[type="file"]');
const pick = (container, file) =>
  fireEvent.change(fileInput(container), { target: { files: [file] } });

const csvFile = (text) => new File([text], 'things.csv', { type: 'text/csv' });

// A real ZIP, built here rather than mocked: the component's own JSZip read is
// half of what the ZIP path does.
async function zipFile(entries) {
  const zip = new JSZip();
  for (const [name, content] of Object.entries(entries)) zip.file(name, content);
  const blob = await zip.generateAsync({ type: 'blob' });
  return new File([blob], 'things.zip', { type: 'application/zip' });
}

function jsonResponse(data, ok = true, status = ok ? 200 : 400) {
  return { ok, status, json: () => Promise.resolve(data) };
}

const renderBulkAdd = (onImported = vi.fn()) => ({
  onImported,
  ...render(<BulkAddCsv collectionCode="COL001" onImported={onImported} />),
});

beforeEach(() => {
  vi.clearAllMocks();
  allowance.perHour = null;
  apiFetch.mockResolvedValue(jsonResponse({ created: 0 }));
});

describe('BulkAddCsv — plain CSV', () => {
  test('the import button sits in a wide row, so on a phone it is the width of the screen', async () => {
    const { container } = renderBulkAdd();

    pick(container, csvFile('headline,type,fee\nCazo de acero,RENT_THING,1\nSartén,SELL_THING,3'));

    const importButton = await screen.findByRole('button', { name: 'Add 2 items' });
    expect(importButton.parentElement).toHaveClass('button-row-wide');
  });

  test('parses, previews, and imports the mapped rows', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ created: 2 }));
    const { container, onImported } = renderBulkAdd();

    pick(container, csvFile('headline,type,fee\nCazo de acero,RENT_THING,1\nSartén,SELL_THING,3'));

    expect(await screen.findByText('Preview (2)')).toBeInTheDocument();
    expect(screen.getByText('Cazo de acero — Rental · 1')).toBeInTheDocument();
    expect(screen.getByText('Sartén — Sale · 3')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Add 2 items'));

    await waitFor(() => expect(onImported).toHaveBeenCalledWith(2));
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/collections/COL001/things/bulk/', {
      method: 'POST',
      body: JSON.stringify({
        rows: [
          { type: 'RENT_THING', headline: 'Cazo de acero', fee: '1' },
          { type: 'SELL_THING', headline: 'Sartén', fee: '3' },
        ],
      }),
    });
  });

  test('a tags cell is split on the pipe and previewed', async () => {
    const { container } = renderBulkAdd();

    pick(container, csvFile('headline,tags\nCazo,Cocina|Vintage'));

    expect(await screen.findByText('Cazo · Cocina, Vintage')).toBeInTheDocument();
  });
});

// Client-side guards. Each must stop the import before any request goes out.
describe('BulkAddCsv — guards', () => {
  test('refuses more than 100 rows', async () => {
    const { container } = renderBulkAdd();
    const rows = Array.from({ length: 101 }, (_, i) => `Thing ${i}`).join('\n');

    pick(container, csvFile(`headline\n${rows}`));

    expect(await screen.findByText('You can import up to 100 items at once.')).toBeInTheDocument();
    expect(screen.queryByText(/^Preview/)).toBeNull();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  test('refuses a row with no headline', async () => {
    const { container } = renderBulkAdd();

    pick(container, csvFile('headline,type\nCazo,GIFT_THING\n,SELL_THING'));

    expect(await screen.findByText('Every row needs a headline.')).toBeInTheDocument();
    expect(screen.queryByText(/^Preview/)).toBeNull();
  });

  test('refuses an empty file', async () => {
    const { container } = renderBulkAdd();

    pick(container, csvFile('headline\n'));

    expect(await screen.findByText('No rows found in that file.')).toBeInTheDocument();
  });
});

describe('BulkAddCsv — ZIP', () => {
  test('uploads each referenced photo and sends its public_id as the thumbnail', async () => {
    uploadImage.mockResolvedValue({ publicId: 'oiueei/things/cazo' });
    apiFetch.mockResolvedValue(jsonResponse({ created: 1 }));
    const { container, onImported } = renderBulkAdd();

    pick(
      container,
      await zipFile({
        'things.csv': 'headline,photo\nCazo,cazo.jpg',
        'cazo.jpg': 'fake-jpeg-bytes',
      })
    );

    expect(await screen.findByText('Preview (1)')).toBeInTheDocument();
    expect(screen.getByText('Cazo · 📷 cazo.jpg')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Add 1 items'));

    await waitFor(() => expect(onImported).toHaveBeenCalledWith(1));

    // The photo travels the same signed upload path as any other image.
    expect(uploadImage).toHaveBeenCalledTimes(1);
    const [uploaded, folder] = uploadImage.mock.calls[0];
    expect(uploaded.name).toBe('cazo.jpg');
    expect(uploaded.type).toBe('image/jpeg');
    expect(folder).toBe('oiueei/things');

    // The filename is swapped for the storage key the upload returned.
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/collections/COL001/things/bulk/', {
      method: 'POST',
      body: JSON.stringify({ rows: [{ headline: 'Cazo', thumbnail: 'oiueei/things/cazo' }] }),
    });
  });

  test('refuses a ZIP whose CSV names a photo the ZIP does not carry', async () => {
    const { container } = renderBulkAdd();

    pick(container, await zipFile({ 'things.csv': 'headline,photo\nCazo,cazo.jpg' }));

    expect(
      await screen.findByText(
        'These photos are named in the CSV but missing from the ZIP: cazo.jpg'
      )
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Preview/)).toBeNull();
  });

  test('refuses a ZIP with no CSV in it', async () => {
    const { container } = renderBulkAdd();

    pick(container, await zipFile({ 'cazo.jpg': 'fake-jpeg-bytes' }));

    expect(await screen.findByText('The ZIP must contain a CSV file.')).toBeInTheDocument();
  });

  test('a failed photo upload stops the import and says so', async () => {
    uploadImage.mockRejectedValue(new Error('upload_failed'));
    const { container, onImported } = renderBulkAdd();

    pick(
      container,
      await zipFile({
        'things.csv': 'headline,photo\nCazo,cazo.jpg',
        'cazo.jpg': 'fake-jpeg-bytes',
      })
    );
    fireEvent.click(await screen.findByText('Add 1 items'));

    expect(
      await screen.findByText("Some photos couldn't be uploaded. Check the images and try again.")
    ).toBeInTheDocument();
    expect(apiFetch).not.toHaveBeenCalled();
    expect(onImported).not.toHaveBeenCalled();
  });
});

// The carousel: a `photos` column of filenames separated by `|`, up to 8 per thing.
describe('BulkAddCsv — the carousel', () => {
  const sentRows = () => JSON.parse(apiFetch.mock.calls[0][1].body).rows;

  beforeEach(() => {
    // Every upload answers with a key named after its file, so what travels can be read back.
    uploadImage.mockImplementation(async (file) => ({ publicId: `oiueei/things/${file.name}` }));
    apiFetch.mockResolvedValue(jsonResponse({ created: 2 }));
  });

  test('a name used by several rows is uploaded once, and each row sends its gallery in order', async () => {
    const { container, onImported } = renderBulkAdd();

    pick(
      container,
      await zipFile({
        'things.csv': 'headline,photo,photos\nA,cover-a.jpg,x.jpg|y.jpg\nB,cover-b.jpg,y.jpg|x.jpg',
        'cover-a.jpg': 'bytes',
        'cover-b.jpg': 'bytes',
        'x.jpg': 'bytes',
        'y.jpg': 'bytes',
      })
    );
    fireEvent.click(await screen.findByText('Add 2 items'));
    await waitFor(() => expect(onImported).toHaveBeenCalledWith(2));

    // Four files for the four distinct names, not six for the six mentions.
    expect(uploadImage.mock.calls.map(([file]) => file.name).sort()).toEqual([
      'cover-a.jpg',
      'cover-b.jpg',
      'x.jpg',
      'y.jpg',
    ]);
    expect(sentRows()).toEqual([
      {
        headline: 'A',
        thumbnail: 'oiueei/things/cover-a.jpg',
        gallery: ['oiueei/things/x.jpg', 'oiueei/things/y.jpg'],
      },
      {
        headline: 'B',
        thumbnail: 'oiueei/things/cover-b.jpg',
        gallery: ['oiueei/things/y.jpg', 'oiueei/things/x.jpg'],
      },
    ]);
    // The filenames never travel: only the keys they uploaded to.
    expect(JSON.stringify(sentRows())).not.toMatch(/"photos?":/);
  });

  test('a carousel with no cover sends the gallery and no thumbnail', async () => {
    const { container, onImported } = renderBulkAdd();

    pick(
      container,
      await zipFile({
        'things.csv': 'headline,photos\nA,x.jpg|y.jpg',
        'x.jpg': 'bytes',
        'y.jpg': 'bytes',
      })
    );
    fireEvent.click(await screen.findByText('Add 1 items'));
    await waitFor(() => expect(onImported).toHaveBeenCalled());

    expect(sentRows()).toEqual([
      { headline: 'A', gallery: ['oiueei/things/x.jpg', 'oiueei/things/y.jpg'] },
    ]);
  });

  test('the preview adds how many extra photos a row carries after its cover', async () => {
    const { container } = renderBulkAdd();

    pick(
      container,
      await zipFile({
        'things.csv': 'headline,photo,photos\nA,cover.jpg,x.jpg|y.jpg\nB,cover.jpg,\nC,,x.jpg',
        'cover.jpg': 'bytes',
        'x.jpg': 'bytes',
        'y.jpg': 'bytes',
      })
    );

    expect(await screen.findByText('A · 📷 cover.jpg +2')).toBeInTheDocument();
    // No carousel: the line is what it was.
    expect(screen.getByText('B · 📷 cover.jpg')).toBeInTheDocument();
    // A carousel and no cover: the count alone.
    expect(screen.getByText('C · 📷 +1')).toBeInTheDocument();
  });

  test('a photo named only in the carousel and missing from the ZIP is refused like a missing cover', async () => {
    const { container } = renderBulkAdd();

    pick(
      container,
      await zipFile({
        'things.csv': 'headline,photo,photos\nA,cover.jpg,here.jpg|gone.jpg',
        'cover.jpg': 'bytes',
        'here.jpg': 'bytes',
      })
    );

    expect(
      await screen.findByText(
        'These photos are named in the CSV but missing from the ZIP: gone.jpg'
      )
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Preview/)).toBeNull();
    expect(uploadImage).not.toHaveBeenCalled();
  });

  test('a row with more than 8 extra photos is refused, and says the limit', async () => {
    const { container } = renderBulkAdd();
    const names = Array.from({ length: 9 }, (_, i) => `p${i}.jpg`);

    pick(
      container,
      await zipFile({
        'things.csv': `headline,photos\nA,${names.join('|')}`,
        ...Object.fromEntries(names.map((name) => [name, 'bytes'])),
      })
    );

    expect(
      await screen.findByText('Each thing takes at most 8 extra photos in the "photos" column.')
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Preview/)).toBeNull();
    expect(uploadImage).not.toHaveBeenCalled();
  });

  test('exactly 8 extra photos is fine', async () => {
    const { container } = renderBulkAdd();
    const names = Array.from({ length: 8 }, (_, i) => `p${i}.jpg`);

    pick(
      container,
      await zipFile({
        'things.csv': `headline,photos\nA,${names.join('|')}`,
        ...Object.fromEntries(names.map((name) => [name, 'bytes'])),
      })
    );

    expect(await screen.findByText('Preview (1)')).toBeInTheDocument();
  });

  test('a plain CSV has no photos: the column is ignored', async () => {
    const { container, onImported } = renderBulkAdd();

    pick(container, csvFile('headline,photos\nA,x.jpg|y.jpg'));
    fireEvent.click(await screen.findByText('Add 1 items'));
    await waitFor(() => expect(onImported).toHaveBeenCalled());

    expect(screen.queryByText(/📷/)).toBeNull();
    expect(uploadImage).not.toHaveBeenCalled();
    expect(sentRows()).toEqual([{ headline: 'A' }]);
  });

  test("the carousels count against the hour's allowance with the covers", async () => {
    // 61 things, a cover and one more photo each: 122 distinct files, over the 120 an
    // hour allows — though only 61 rows, well within the 100 a file may hold.
    const rows = Array.from({ length: 61 }, (_, i) => `T${i},c${i}.jpg,g${i}.jpg`);
    const files = Object.fromEntries(
      Array.from({ length: 61 }, (_, i) => [
        [`c${i}.jpg`, 'b'],
        [`g${i}.jpg`, 'b'],
      ]).flat()
    );
    const { container } = renderBulkAdd();

    pick(
      container,
      await zipFile({ 'things.csv': `headline,photo,photos\n${rows.join('\n')}`, ...files })
    );

    expect(
      await screen.findByText(
        'This ZIP has 122 photos and you can upload 120 an hour. Split it into several and upload them an hour apart.'
      )
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Preview/)).toBeNull();
  });

  test('exactly 120 distinct photos is still imported', async () => {
    const rows = Array.from({ length: 60 }, (_, i) => `T${i},c${i}.jpg,g${i}.jpg`);
    const files = Object.fromEntries(
      Array.from({ length: 60 }, (_, i) => [
        [`c${i}.jpg`, 'b'],
        [`g${i}.jpg`, 'b'],
      ]).flat()
    );
    const { container } = renderBulkAdd();

    pick(
      container,
      await zipFile({ 'things.csv': `headline,photo,photos\n${rows.join('\n')}`, ...files })
    );

    expect(await screen.findByText('Preview (60)')).toBeInTheDocument();
  });
});

// An hour allows `UPLOADS_PER_HOUR` tickets and every photo of a ZIP takes one.
describe("BulkAddCsv — the hour's allowance of photos", () => {
  const photosZip = (count) =>
    zipFile({
      'things.csv': `headline,photo\n${Array.from({ length: count }, (_, i) => `Thing ${i},p${i}.jpg`).join('\n')}`,
      ...Object.fromEntries(Array.from({ length: count }, (_, i) => [`p${i}.jpg`, 'bytes'])),
    });

  test('a ZIP with more photos than an hour allows gets no preview and says how many', async () => {
    allowance.perHour = 2;
    const { container } = renderBulkAdd();

    pick(container, await photosZip(3));

    expect(
      await screen.findByText(
        'This ZIP has 3 photos and you can upload 2 an hour. Split it into several and upload them an hour apart.'
      )
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Preview/)).toBeNull();
    expect(uploadImage).not.toHaveBeenCalled();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  test('exactly the allowance is still imported', async () => {
    allowance.perHour = 2;
    const { container } = renderBulkAdd();

    pick(container, await photosZip(2));

    expect(await screen.findByText('Preview (2)')).toBeInTheDocument();
  });

  test('a photo used by several rows counts once', async () => {
    allowance.perHour = 1;
    const { container } = renderBulkAdd();

    pick(
      container,
      await zipFile({
        'things.csv': 'headline,photo\nA,same.jpg\nB,same.jpg\nC,same.jpg',
        'same.jpg': 'bytes',
      })
    );

    expect(await screen.findByText('Preview (3)')).toBeInTheDocument();
  });

  test('a ticket refused with a 429 mid-import says the hour is used up, and sends no bulk', async () => {
    uploadImage.mockRejectedValue(new UploadRateLimitedError());
    const { container, onImported } = renderBulkAdd();

    pick(
      container,
      await zipFile({
        'things.csv': 'headline,photo\nCazo,cazo.jpg',
        'cazo.jpg': 'fake-jpeg-bytes',
      })
    );
    fireEvent.click(await screen.findByText('Add 1 items'));

    expect(
      await screen.findByText(
        "You've reached the limit of 120 photos an hour, so nothing was added. Try again in a while."
      )
    ).toBeInTheDocument();
    expect(screen.queryByText(/Some photos couldn't be uploaded/)).toBeNull();
    expect(apiFetch).not.toHaveBeenCalled();
    expect(onImported).not.toHaveBeenCalled();
  });
});

// The import is atomic server-side, so a rejection means nothing was created —
// the user has to be told which rows to fix.
describe('BulkAddCsv — server rejections', () => {
  test('surfaces the error detail from a 400', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({ error: 'Tag "Cocina" is not in this collection.' }, false)
    );
    const { container, onImported } = renderBulkAdd();

    pick(container, csvFile('headline\nCazo'));
    fireEvent.click(await screen.findByText('Add 1 items'));

    expect(await screen.findByText('Tag "Cocina" is not in this collection.')).toBeInTheDocument();
    expect(onImported).not.toHaveBeenCalled();
  });

  test('names the offending rows, numbered as the preview shows them', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ errors: [{ row: 0 }, { row: 2 }] }, false));
    const { container } = renderBulkAdd();

    pick(container, csvFile('headline\nCazo\nSartén\nOlla'));
    fireEvent.click(await screen.findByText('Add 3 items'));

    // The server counts rows from 0, the preview list from 1.
    expect(
      await screen.findByText("These rows couldn't be imported (check their columns): 1, 3")
    ).toBeInTheDocument();
  });

  test('surfaces a rate limit', async () => {
    apiFetch.mockResolvedValue(jsonResponse({}, false, 429));
    const { container } = renderBulkAdd();

    pick(container, csvFile('headline\nCazo'));
    fireEvent.click(await screen.findByText('Add 1 items'));

    expect(
      await screen.findByText('Too many attempts — please wait a moment and try again.')
    ).toBeInTheDocument();
  });

  test('surfaces a dropped connection', async () => {
    apiFetch.mockRejectedValue(new Error('network down'));
    const { container } = renderBulkAdd();

    pick(container, csvFile('headline\nCazo'));
    fireEvent.click(await screen.findByText('Add 1 items'));

    expect(await screen.findByText('Connection error.')).toBeInTheDocument();
  });
});
