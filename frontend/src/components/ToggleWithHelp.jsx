import { ToggleButton } from 'hds-react';

/**
 * An HDS inline ToggleButton whose label is the title alone, with the explanation in a
 * paragraph of its own underneath, tied to the button by `aria-describedby`. HDS has no
 * helper text of its own for this component.
 */
export default function ToggleWithHelp({ id, help, ...props }) {
  const helpId = help ? `${id}-help` : undefined;
  return (
    <div className="toggle-with-help">
      <ToggleButton id={id} variant="inline" aria-describedby={helpId} {...props} />
      {help && (
        <p id={helpId} className="toggle-help">
          {help}
        </p>
      )}
    </div>
  );
}
