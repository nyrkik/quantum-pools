"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  CreditCard,
  Copy,
  Check,
  Trash2,
  Loader2,
  ExternalLink,
} from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

interface BillingTileProps {
  customerId: string;
  autopayEnabled: boolean;
  hasPaymentMethod: boolean;
  cardLast4: string | null;
  cardBrand: string | null;
  cardExpMonth: number | null;
  cardExpYear: number | null;
  nextBillingDate: string | null;
  billingDayOfMonth: number;
  billingFrequency: string;
  monthlyRate: number;
  autopayFailureCount: number;
  onUpdate: () => void;
}

export function BillingTile({
  customerId,
  autopayEnabled,
  hasPaymentMethod,
  cardLast4,
  cardBrand,
  cardExpMonth,
  cardExpYear,
  nextBillingDate,
  billingFrequency,
  monthlyRate,
  autopayFailureCount,
  onUpdate,
}: BillingTileProps) {
  const [sendingLink, setSendingLink] = useState(false);
  const [copied, setCopied] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [toggling, setToggling] = useState(false);

  const handleSendSetupLink = async () => {
    setSendingLink(true);
    try {
      const result = await api.post<{ card_setup_url: string }>(
        `/v1/customers/${customerId}/setup-intent`
      );
      await navigator.clipboard.writeText(result.card_setup_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    } catch {
      // Silently fail — could show toast
    } finally {
      setSendingLink(false);
    }
  };

  const handleRemoveCard = async () => {
    setRemoving(true);
    try {
      await api.delete(`/v1/customers/${customerId}/payment-method`);
      onUpdate();
    } catch {
      // Error handling
    } finally {
      setRemoving(false);
    }
  };

  const handleToggleAutopay = async () => {
    setToggling(true);
    try {
      await api.put(`/v1/customers/${customerId}`, {
        autopay_enabled: !autopayEnabled,
      });
      onUpdate();
    } catch {
      // Error handling
    } finally {
      setToggling(false);
    }
  };

  const formatBrand = (brand: string | null) => {
    if (!brand) return "Card";
    return brand.charAt(0).toUpperCase() + brand.slice(1);
  };

  const freqLabel = billingFrequency.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-sm font-semibold">
          <div className="flex items-center gap-2">
            <CreditCard className="h-4 w-4 text-muted-foreground" />
            Billing & Payments
          </div>
          {autopayEnabled && hasPaymentMethod && (
            <Badge variant="default" className="text-[10px]">AutoPay</Badge>
          )}
          {autopayFailureCount > 0 && (
            <Badge variant="outline" className="border-red-400 text-red-600 text-[10px]">
              Payment Failed
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Rate summary */}
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">{freqLabel} Rate</span>
          <span className="font-medium">${monthlyRate.toFixed(2)}</span>
        </div>

        {nextBillingDate && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Next Billing</span>
            <span className="text-sm">
              {new Date(nextBillingDate + "T00:00:00").toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </span>
          </div>
        )}

        {/* Saved card */}
        {hasPaymentMethod ? (
          <div className="bg-muted/50 rounded-lg p-3 flex items-center gap-3">
            <CreditCard className="h-4 w-4 text-muted-foreground shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">
                {formatBrand(cardBrand)} ending in {cardLast4}
              </p>
              {cardExpMonth && cardExpYear && (
                <p className="text-xs text-muted-foreground">
                  Expires {cardExpMonth}/{cardExpYear}
                </p>
              )}
            </div>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="ghost" size="icon" disabled={removing}>
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Remove Card</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will remove the saved card and disable AutoPay. The customer will need to save a new card to re-enable automatic payments.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleRemoveCard}>Remove</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        ) : (
          <div className="bg-muted/50 rounded-lg p-3 text-center">
            <p className="text-xs text-muted-foreground">No card on file</p>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="flex-1 gap-1.5"
            onClick={handleSendSetupLink}
            disabled={sendingLink}
          >
            {sendingLink ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : copied ? (
              <Check className="h-3.5 w-3.5 text-green-600" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
            {copied ? "Link Copied!" : "Card Setup Link"}
          </Button>

          {hasPaymentMethod && (
            <Button
              variant={autopayEnabled ? "default" : "outline"}
              size="sm"
              className="gap-1.5"
              onClick={handleToggleAutopay}
              disabled={toggling}
            >
              {toggling && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {autopayEnabled ? "AutoPay On" : "Enable AutoPay"}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
