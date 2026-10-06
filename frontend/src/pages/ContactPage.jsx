import ContactFormPage from '../components/ContactFormPage';

/**
 * The support channel (`/contact`): the shared operator-message form with the
 * support copy. It used to end with a quiet pointer to a collaborate page, which
 * left the front end on 2026-10-04; the form is all there is.
 */
export default function ContactPage() {
  return (
    <ContactFormPage
      docTitleKey="titles.contact"
      titleKey="contact.pageTitle"
      introKey="contact.intro"
      idPrefix="contact"
    />
  );
}
