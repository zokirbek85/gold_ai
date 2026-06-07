import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPrice(price: number | null | undefined, decimals = 2): string {
  if (price == null) return "—";
  return price.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export function formatPct(value: number | null | undefined, decimals = 1): string {
  if (value == null) return "—";
  return `${value.toFixed(decimals)}%`;
}

export function signalColor(type: string): string {
  if (type === "BUY") return "text-green-400";
  if (type === "SELL") return "text-red-400";
  return "text-gray-400";
}

export function directionColor(direction: string): string {
  if (direction === "bullish") return "text-green-400";
  if (direction === "bearish") return "text-red-400";
  return "text-gray-400";
}
