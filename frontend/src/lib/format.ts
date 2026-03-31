/**
 * Format a number in Indian lakh system: 1,23,456.00
 */
export function formatINR(value: string | number | null | undefined): string {
  if (value == null || value === "") return "\u20B90.00";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "\u20B90.00";

  const isNeg = num < 0;
  const abs = Math.abs(num);
  const [intPart, decPart] = abs.toFixed(2).split(".");

  // Indian grouping: last 3, then groups of 2
  let result = "";
  const len = intPart.length;
  if (len <= 3) {
    result = intPart;
  } else {
    result = intPart.slice(-3);
    let remaining = intPart.slice(0, -3);
    while (remaining.length > 2) {
      result = remaining.slice(-2) + "," + result;
      remaining = remaining.slice(0, -2);
    }
    if (remaining.length > 0) {
      result = remaining + "," + result;
    }
  }

  return `${isNeg ? "-" : ""}\u20B9${result}.${decPart}`;
}

/**
 * Format a status string for display
 */
export function formatStatus(status: string): string {
  return status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Get status color class
 */
export function getStatusColor(status: string): string {
  switch (status) {
    case "ca_approved":
    case "ca_overridden":
      return "status-green";
    case "ca_rejected":
    case "failed":
      return "status-red";
    case "flagged_low_confidence":
    case "flagged_classification":
    case "flagged_anomaly":
      return "status-red";
    case "pending_ca_review":
    case "pending_client_confirmation":
    case "processing":
    case "queued":
      return "status-yellow";
    default:
      return "status-yellow";
  }
}
