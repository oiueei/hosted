import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import { installStaleChunkReload } from './utils/reloadOnStaleChunk.js';

// Before the first render: a lazy page can fail to load as soon as it mounts.
installStaleChunkReload();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>
);
