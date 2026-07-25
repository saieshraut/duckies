export function inr(n) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency", currency: "INR", maximumFractionDigits: 0,
  }).format(Number(n || 0));
}
export function inr2(n) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency", currency: "INR", minimumFractionDigits: 2,
  }).format(Number(n || 0));
}
export function dateLabel(d) {
  if (!d) return "";
  return new Date(d).toLocaleDateString("en-IN", {
    weekday: "short", day: "numeric", month: "short",
  });
}
export function timeLabel(t) {
  if (!t) return "";
  const [h, m] = String(t).split(":");
  const hr = ((+h % 12) || 12), ap = +h < 12 ? "AM" : "PM";
  return `${hr}:${m} ${ap}`;
}
