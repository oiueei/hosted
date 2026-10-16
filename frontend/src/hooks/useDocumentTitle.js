import { useEffect } from 'react';

/**
 * Sets the browser tab's title to `title`, and again whenever it changes. An empty
 * or missing title leaves the tab as it is: a page that has no name for itself yet
 * must not blank the one it inherited.
 *
 * Pass the text already resolved — `useDocumentTitle(t('titles.home'))` — so the
 * title follows the language and whatever it is built from (a collection's name)
 * without the page listing them as dependencies.
 */
export default function useDocumentTitle(title) {
  useEffect(() => {
    if (title) document.title = title;
  }, [title]);
}
