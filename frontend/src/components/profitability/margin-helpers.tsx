import { Badge } from "@/components/ui/badge";

export function marginColor(margin: number, target: number) {
  if (margin >= target) return "text-green-600";
  if (margin >= target * 0.7) return "text-yellow-600";
  return "text-red-600";
}

export function marginBadge(margin: number, target: number) {
  if (margin >= target)
    return <Badge className="bg-green-100 text-green-800 hover:bg-green-100">{margin.toFixed(1)}%</Badge>;
  if (margin >= 0)
    return <Badge className="bg-yellow-100 text-yellow-800 hover:bg-yellow-100">{margin.toFixed(1)}%</Badge>;
  return <Badge className="bg-red-100 text-red-800 hover:bg-red-100">{margin.toFixed(1)}%</Badge>;
}
