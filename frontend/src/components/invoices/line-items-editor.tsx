"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Plus, Trash2 } from "lucide-react";
import { formatCurrency } from "@/lib/format";

export interface LineItem {
  description: string;
  quantity: number;
  unit_price: number;
  is_taxed: boolean;
}

interface LineItemsEditorProps {
  items: LineItem[];
  onChange: (items: LineItem[]) => void;
}

export function LineItemsEditor({ items, onChange }: LineItemsEditorProps) {
  const updateItem = (index: number, field: keyof LineItem, value: string | number | boolean) => {
    onChange(items.map((item, i) => (i === index ? { ...item, [field]: value } : item)));
  };

  const addItem = () => {
    onChange([...items, { description: "", quantity: 1, unit_price: 0, is_taxed: false }]);
  };

  const removeItem = (index: number) => {
    if (items.length <= 1) return;
    onChange(items.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-3">
      {/* Desktop table view */}
      <div className="hidden sm:block rounded-md border">
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-100 dark:bg-slate-800">
              <TableHead className="text-xs font-medium uppercase tracking-wide">Description</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide w-20 text-right">Qty</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide w-28 text-right">Unit Price</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide w-24 text-right">Amount</TableHead>
              <TableHead className="text-xs font-medium uppercase tracking-wide w-14 text-center">Tax</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item, i) => (
              <TableRow key={i} className={`hover:bg-blue-50 dark:hover:bg-blue-950 ${i % 2 === 1 ? "bg-slate-50 dark:bg-slate-900" : ""}`}>
                <TableCell className="p-1.5">
                  <Input
                    value={item.description}
                    onChange={(e) => updateItem(i, "description", e.target.value)}
                    placeholder="Service description"
                    className="h-8 text-sm border-0 bg-transparent focus-visible:ring-1"
                  />
                </TableCell>
                <TableCell className="p-1.5">
                  <Input
                    type="number"
                    value={item.quantity}
                    onChange={(e) => updateItem(i, "quantity", parseFloat(e.target.value) || 0)}
                    min="0"
                    step="1"
                    className="h-8 text-sm text-right border-0 bg-transparent focus-visible:ring-1 w-full"
                  />
                </TableCell>
                <TableCell className="p-1.5">
                  <Input
                    type="number"
                    value={item.unit_price}
                    onChange={(e) => updateItem(i, "unit_price", parseFloat(e.target.value) || 0)}
                    min="0"
                    step="0.01"
                    className="h-8 text-sm text-right border-0 bg-transparent focus-visible:ring-1 w-full"
                  />
                </TableCell>
                <TableCell className="p-1.5 text-right text-sm text-muted-foreground">
                  {formatCurrency(item.quantity * item.unit_price)}
                </TableCell>
                <TableCell className="p-1.5 text-center">
                  <Checkbox
                    checked={item.is_taxed}
                    onCheckedChange={(checked) => updateItem(i, "is_taxed", checked === true)}
                  />
                </TableCell>
                <TableCell className="p-1.5">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-destructive"
                    onClick={() => removeItem(i)}
                    disabled={items.length <= 1}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Mobile card view */}
      <div className="sm:hidden space-y-3">
        {items.map((item, i) => (
          <div key={i} className="bg-muted/50 rounded-md p-3 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <Input
                value={item.description}
                onChange={(e) => updateItem(i, "description", e.target.value)}
                placeholder="Service description"
                className="h-8 text-sm flex-1"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-muted-foreground hover:text-destructive flex-shrink-0"
                onClick={() => removeItem(i)}
                disabled={items.length <= 1}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1">
                <label className="text-[10px] text-muted-foreground uppercase">Qty</label>
                <Input
                  type="number"
                  value={item.quantity}
                  onChange={(e) => updateItem(i, "quantity", parseFloat(e.target.value) || 0)}
                  min="0"
                  step="1"
                  className="h-8 text-sm"
                />
              </div>
              <div className="flex-1">
                <label className="text-[10px] text-muted-foreground uppercase">Price</label>
                <Input
                  type="number"
                  value={item.unit_price}
                  onChange={(e) => updateItem(i, "unit_price", parseFloat(e.target.value) || 0)}
                  min="0"
                  step="0.01"
                  className="h-8 text-sm"
                />
              </div>
              <div className="flex-shrink-0 text-right pt-3">
                <span className="text-sm font-medium">{formatCurrency(item.quantity * item.unit_price)}</span>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <Checkbox
                checked={item.is_taxed}
                onCheckedChange={(checked) => updateItem(i, "is_taxed", checked === true)}
              />
              <span className="text-xs text-muted-foreground">Taxable</span>
            </div>
          </div>
        ))}
      </div>

      <Button type="button" variant="outline" size="sm" onClick={addItem}>
        <Plus className="h-3.5 w-3.5 mr-1.5" />
        Add Line Item
      </Button>
    </div>
  );
}
