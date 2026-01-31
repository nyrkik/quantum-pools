"use client";

import { useAuth } from "@/lib/auth-context";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Users, MapPin, CalendarCheck, DollarSign } from "lucide-react";

const stats = [
  {
    title: "Total Customers",
    value: "0",
    description: "Active accounts",
    icon: Users,
  },
  {
    title: "Properties",
    value: "0",
    description: "Service locations",
    icon: MapPin,
  },
  {
    title: "Today's Visits",
    value: "0",
    description: "Scheduled stops",
    icon: CalendarCheck,
  },
  {
    title: "Monthly Revenue",
    value: "$0",
    description: "Current period",
    icon: DollarSign,
  },
];

export default function DashboardPage() {
  const { user, organizationName } = useAuth();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Welcome back, {user?.first_name}. Here&apos;s your{" "}
          {organizationName} overview.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
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
            <CardTitle>Recent Activity</CardTitle>
            <CardDescription>Latest service visits and updates</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              No recent activity yet. Start by adding customers and properties.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Upcoming Visits</CardTitle>
            <CardDescription>Scheduled for today</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              No visits scheduled. Set up routes to get started.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
