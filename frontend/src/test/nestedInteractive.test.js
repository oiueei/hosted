import { describe, test, expect, beforeEach } from 'vitest';
import { nestedTabStops } from './nestedInteractive';

/**
 * The detector behind the invariant in `smoke.test.jsx` and
 * `a11yInteractive.test.jsx`. It is tested on its own for the reason
 * `scripts/audit-gate.test.js` gives for the audit gate: a check nobody checks
 * can quietly stop checking, and the failure looks exactly like a green build.
 * That is not hypothetical here — it is precisely what axe did for a year.
 */

let root;
beforeEach(() => {
  root = document.createElement('div');
  document.body.appendChild(root);
});

const html = (markup) => {
  root.innerHTML = markup;
  return nestedTabStops(root);
};

describe('what it catches', () => {
  test('a link wrapping a button — the shape that got past axe 28 times', () => {
    expect(html('<a href="/new"><button>Create collection</button></a>')).toEqual([
      'a › button — “Create collection”',
    ]);
  });

  test('the same nesting the other way round', () => {
    expect(html('<button>Open <a href="/help">help</a></button>')).toEqual([
      'button › a — “Open help”',
    ]);
  });

  test('a custom widget that opted into the tab order and holds a control', () => {
    expect(html('<div tabindex="0" role="button">Card <button>Buy</button></div>')).toEqual([
      'div[role=button] › button — “Card Buy”',
    ]);
  });

  test('it reaches nesting at any depth, not just the direct child', () => {
    expect(html('<a href="/x"><span><em><button>Deep</button></em></span></a>')).toEqual([
      'a › button — “Deep”',
    ]);
  });

  test('an aria-label names the control, since that is what is announced', () => {
    expect(html('<a href="/x" aria-label="Go home"><button>→</button></a>')).toEqual([
      'a › button — “Go home”',
    ]);
  });

  test('one entry per shape, however many times it repeats', () => {
    expect(
      html(
        '<a href="/1"><button>Edit</button></a>' +
          '<a href="/2"><button>Edit</button></a>' +
          '<a href="/3"><button>Edit</button></a>'
      )
    ).toEqual(['a › button — “Edit”']);
  });
});

describe('what it must not flag', () => {
  test('two controls side by side', () => {
    expect(html('<a href="/x">Link</a><button>Button</button>')).toEqual([]);
  });

  test("HDS's Linkbox — the inner link is tabindex=-1, so it steals no stop", () => {
    // Its defect is the role="region", which is a different failure with a
    // different fix. Conflating the two would make this test unfixable.
    expect(html('<div role="region" tabindex="0"><a href="/c" tabindex="-1">Go</a></div>')).toEqual(
      []
    );
  });

  test('a disabled inner control is not in the tab order', () => {
    expect(html('<a href="/x"><button disabled>Off</button></a>')).toEqual([]);
  });

  test('aria-disabled counts too — ImageCarousel keeps its arrows focusable that way', () => {
    expect(html('<a href="/x"><button aria-disabled="true">Off</button></a>')).toEqual([]);
  });

  test('a subtree hidden from assistive tech', () => {
    expect(html('<div aria-hidden="true"><a href="/x"><button>Ghost</button></a></div>')).toEqual(
      []
    );
  });

  test('an anchor with no href is not a tab stop', () => {
    expect(html('<a><button>Not a link</button></a>')).toEqual([]);
  });

  test('a form with several fields, which is not nesting at all', () => {
    expect(
      html('<form><input id="a"><textarea></textarea><select></select><button>Save</button></form>')
    ).toEqual([]);
  });
});
