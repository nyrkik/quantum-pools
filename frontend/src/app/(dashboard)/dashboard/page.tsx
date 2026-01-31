"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Users, MapPin, CalendarCheck, DollarSign, Plus } from "lucide-react";

interface Stats {
  customers: number;
  properties: number;
  todayVisits: number;
  monthlyRevenue: number;
}

export default function DashboardPage() {
  const { user, organizationName } = useAuth();
  const [stats, setStats] = useState<Stats>({
    customers: 0,
    properties: 0,
    todayVisits: 0,
    monthlyRevenue: 0,
  });

  useEffect(() => {
    (async () => {
      try {
        const [customers, properties, visits] = await Promise.all([
          api.get<{ total: number }>("/v1/customers?limit=1"),
          api.get<{ total: number }>("/v1/properties?limit=1"),
          api.get<{ total: number }>(
            `/v1/visits?scheduled_date=${new Date().toISOString().split("T")[0]}&limit=1`
          ),
        ]);
        setStats({
          customers: customers.total,
          properties: properties.total,
          todayVisits: visits.total,
          monthlyRevenue: 0,
        });
      } catch {
        // Stats will stay at 0
      }
    })();
  }, []);

  const statCards = [
    {
      title: "Total Customers",
      value: stats.customers.toString(),
      description: "Active accounts",
      icon: Users,
    },
    {
      title: "Properties",
      value: stats.properties.toString(),
      description: "Service locations",
      icon: MapPin,
    },
    {
      title: "Today's Visits",
      value: stats.todayVisits.toString(),
      description: "Scheduled stops",
      icon: CalendarCheck,
    },
    {
      title: "Monthly Revenue",
      value: `$${stats.monthlyRevenue.toLocaleString()}`,
      description: "Current period",
      icon: DollarSign,
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">
            Welcome back, {user?.first_name}. Here&apos;s your{" "}
            {organizationName} overview.
          </p>
        </div>
        <Link href="/customers">
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            Add Customer
          </Button>
        </Link>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((stat) => (
          <Card key={stat.title}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">
                {stat.title}
              </CardTitle>
              <stat.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
              <CardDescription>{stat.description}</CardDescription>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Quick Actions</CardTitle>
            <CardDescription>Common tasks</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Link href="/customers">
              <Button variant="outline" size="sm">
                <Users className="mr-2 h-4 w-4" />
                Customers
              </Button>
            </Link>
            <Link href="/properties">
              <Button variant="outline" size="sm">
                <MapPin className="mr-2 h-4 w-4" />
                Properties
              </Button>
            </Link>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Today&apos;s Visits</CardTitle>
            <CardDescription>Scheduled for today</CardDescription>
          </CardHeader>
          <CardContent>
            {stats.todayVisits === 0 ? (
              <p className="text-sm text-muted-foreground">
                No visits scheduled for today.
              </p>
            ) : (
              <p className="text-sm">
                {stats.todayVisits} visit
                {stats.todayVisits !== 1 ? "s" : ""} scheduled.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
