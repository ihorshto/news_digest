import { Link } from "react-router";
import { EmptyState, Button } from "../components/ui";
import { t } from "../i18n/uk";

export default function NotFoundPage() {
  return (
    <EmptyState
      title={t.notFound.title}
      action={
        <Link to="/">
          <Button variant="secondary">{t.notFound.back}</Button>
        </Link>
      }
    />
  );
}
