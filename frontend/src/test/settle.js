import { act, fireEvent } from '@testing-library/react';

/**
 * Lets the requests a render started finish, inside `act`, so the state they set
 * lands while the test is still watching and not after it has ended.
 *
 * It waits on something concrete: the mocked network. Each round waits for every
 * answer the mocks have handed out so far (a reply that takes its time included),
 * then yields to the event loop; if those replies made the page ask for something
 * more, the mocks' call count has grown and it goes round again, and it stops once a
 * round asks for nothing new. `mocks` are the `vi.fn()`s standing in for the network
 * (`apiFetch`, `fetch`).
 */
export async function settle(...mocks) {
  const calls = () => mocks.reduce((sum, mock) => sum + mock.mock.calls.length, 0);
  const answers = () =>
    mocks.flatMap((mock) => mock.mock.results.map((result) => result.value)).filter(Boolean);
  let seen = -1;
  for (let round = 0; round < 25 && seen !== calls(); round += 1) {
    seen = calls();
    await act(async () => {
      await Promise.allSettled(answers());
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
}

/**
 * Switches the interface language inside `act`: every mounted component that
 * reads `t` re-renders on the change, and outside `act` each one of them warns.
 */
export async function switchLanguage(i18n, language) {
  await act(() => i18n.changeLanguage(language));
}

/**
 * A click inside `act`, for a press that starts a request: the answer sets state a
 * moment after the click, and outside `act` that update is reported as a mistake.
 */
export async function press(element, init) {
  await act(async () => {
    fireEvent.click(element, init);
  });
}
