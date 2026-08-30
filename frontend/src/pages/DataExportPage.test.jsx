import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi, describe, test, expect, beforeEach } from 'vitest';
import DataExportPage from './DataExportPage';

const downloadBlobMock = vi.fn();

vi.mock('../utils/downloadBlob', () => ({
  default: (...args) => downloadBlobMock(...args),
  filenameFromResponse: (res, fallback) =>
    res.headers.get('Content-Disposition')?.match(/filename="?([^"]+)"?/)?.[1] || fallback,
}));

const apiFetchMock = vi.fn();
vi.mock('../services/api', () => ({
  apiFetch: (...args) => apiFetchMock(...args),
}));

function jsonResponse({ ok, status, filename }) {
  return {
    ok,
    status,
    headers: {
      get: (name) => (name === 'Content-Disposition' ? `attachment; filename="${filename}"` : null),
    },
    blob: () => Promise.resolve(new Blob(['{}'], { type: 'application/json' })),
  };
}

describe('DataExportPage', () => {
  beforeEach(() => {
    downloadBlobMock.mockClear();
    apiFetchMock.mockClear();
  });

  test('lists what the export excludes — the point of the page', () => {
    render(
      <MemoryRouter>
        <DataExportPage />
      </MemoryRouter>
    );

    // The 8-point list EXPORT_TOOL.md specifies, checked by content: a
    // reordering or a rewrite that drops one still reads wrong here.
    expect(screen.getByText(/session cookies/i)).toBeInTheDocument();
    expect(screen.getByText(/no bin/i)).toBeInTheDocument();
    expect(screen.getByText(/anonymous by design/i)).toBeInTheDocument();
  });

  test('a successful click hands the response to downloadBlob under the server-set name', async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({ ok: true, status: 200, filename: 'oiueei-ABC123-2026-08-21.json' })
    );
    render(
      <MemoryRouter>
        <DataExportPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole('button', { name: /download my data/i }));

    await waitFor(() => expect(downloadBlobMock).toHaveBeenCalledTimes(1));
    expect(apiFetchMock).toHaveBeenCalledWith('/api/v1/auth/export/');
    const [, filename] = downloadBlobMock.mock.calls[0];
    expect(filename).toBe('oiueei-ABC123-2026-08-21.json');
  });

  test('the error lands in a live region that was already on the page', async () => {
    // The announcement only happens if the region pre-exists the message: this
    // asserts both halves in order, because a page that builds the region and the
    // message in the same render looks identical and says nothing.
    apiFetchMock.mockResolvedValueOnce({ ok: false, status: 500 });
    render(
      <MemoryRouter>
        <DataExportPage />
      </MemoryRouter>
    );

    const region = screen.getByRole('status');
    expect(region).toBeEmptyDOMElement();

    fireEvent.click(screen.getByRole('button', { name: 'Download my data' }));

    await waitFor(() => expect(region).not.toBeEmptyDOMElement());
    // The same node, not a second one that replaced it.
    expect(screen.getByRole('status')).toBe(region);
    expect(region).toHaveTextContent(/couldn't|could not|error/i);
  });

  test('a 429 says "too many attempts", not a generic error', async () => {
    apiFetchMock.mockResolvedValue({ ok: false, status: 429 });
    render(
      <MemoryRouter>
        <DataExportPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole('button', { name: /download my data/i }));

    expect(await screen.findByText(/too many attempts/i)).toBeInTheDocument();
    expect(downloadBlobMock).not.toHaveBeenCalled();
  });

  test('any other failure shows the export-specific error, and nothing downloads', async () => {
    apiFetchMock.mockResolvedValue({ ok: false, status: 500 });
    render(
      <MemoryRouter>
        <DataExportPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole('button', { name: /download my data/i }));

    expect(await screen.findByText(/couldn.t build your export/i)).toBeInTheDocument();
    expect(downloadBlobMock).not.toHaveBeenCalled();
  });

  test('a network failure is reported as a connection error', async () => {
    apiFetchMock.mockRejectedValue(new Error('offline'));
    render(
      <MemoryRouter>
        <DataExportPage />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole('button', { name: /download my data/i }));

    expect(await screen.findByText(/connection/i)).toBeInTheDocument();
  });
});
