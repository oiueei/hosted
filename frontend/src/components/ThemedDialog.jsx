import { Dialog } from 'hds-react';
import useTheeeme from '../hooks/useTheeeme';

/**
 * HDS `Dialog` with its top line in the viewer's primary theeeme colour
 * (`color_01`, the fill of the primary button the dialog already carries) instead
 * of HDS's blue. Decoration, so no contrast requirement. Takes `Dialog`'s props
 * and parts (`ThemedDialog.Header`, `.Content`, `.ActionButtons`).
 */
export default function ThemedDialog(props) {
  const { tc } = useTheeeme();
  const theme = tc.color_01 ? { '--accent-line-color': `var(--color-${tc.color_01})` } : undefined;
  return <Dialog theme={theme} {...props} />;
}

ThemedDialog.Header = Dialog.Header;
ThemedDialog.Content = Dialog.Content;
ThemedDialog.ActionButtons = Dialog.ActionButtons;
