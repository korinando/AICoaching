/** The first letter of the user's name in a circle. One place, so the sidebar and the account
 * page always match (and a photo can replace the letter here later). */
export function Avatar({
  name,
  size = "sm",
}: {
  name: string | undefined;
  size?: "sm" | "lg";
}) {
  return (
    <span
      aria-hidden
      className={`flex shrink-0 items-center justify-center rounded-full bg-accent-soft font-semibold text-accent ${
        size === "lg" ? "h-16 w-16 text-2xl" : "h-8 w-8 text-sm"
      }`}
    >
      {name?.charAt(0).toUpperCase() ?? ""}
    </span>
  );
}
