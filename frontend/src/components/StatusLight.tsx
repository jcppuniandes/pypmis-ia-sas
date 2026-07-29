export default function StatusLight({ value }: { value: number }) {
  const className = value < 0.9 ? "light red" : value < 1 ? "light amber" : "light green";
  return <span className={className} />;
}
