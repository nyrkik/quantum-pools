"use client";

import { useCallback } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";
import type { OptimizationRoute, OptimizationStop } from "@/types/route";

interface RouteEditorProps {
  routes: OptimizationRoute[];
  onReorder: (techId: string, oldIndex: number, newIndex: number) => void;
  onReassign: (stopPropertyId: string, fromTechId: string, toTechId: string) => void;
}

function SortableStop({
  stop,
  techColor,
}: {
  stop: OptimizationStop;
  techColor: string;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: `${stop.property_id}-${stop.sequence}` });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-2 rounded-md border bg-card p-2 text-sm"
    >
      <button {...attributes} {...listeners} className="cursor-grab text-muted-foreground">
        <GripVertical className="h-4 w-4" />
      </button>
      <div
        className="h-5 w-5 flex-shrink-0 rounded-full text-[10px] font-bold text-white flex items-center justify-center"
        style={{ background: techColor }}
      >
        {stop.sequence}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{stop.customer_name || "Unknown"}</p>
        <p className="truncate text-muted-foreground text-xs">
          {stop.property_address}
        </p>
      </div>
      <div className="text-right text-xs text-muted-foreground flex-shrink-0">
        <p>{stop.estimated_service_duration}m svc</p>
        {stop.estimated_drive_time_from_previous > 0 && (
          <p>{stop.estimated_drive_time_from_previous}m drive</p>
        )}
      </div>
    </div>
  );
}

function TechColumn({
  route,
  onReorder,
}: {
  route: OptimizationRoute;
  onReorder: (oldIndex: number, newIndex: number) => void;
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = route.stops.findIndex(
      (s) => `${s.property_id}-${s.sequence}` === active.id
    );
    const newIndex = route.stops.findIndex(
      (s) => `${s.property_id}-${s.sequence}` === over.id
    );
    if (oldIndex !== -1 && newIndex !== -1) {
      onReorder(oldIndex, newIndex);
    }
  };

  const ids = route.stops.map((s) => `${s.property_id}-${s.sequence}`);

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <div
          className="h-3 w-3 rounded-full"
          style={{ background: route.tech_color }}
        />
        <h3 className="text-sm font-semibold">{route.tech_name}</h3>
        <span className="text-xs text-muted-foreground">
          {route.total_stops} stops &middot; {route.total_distance_miles} mi &middot;{" "}
          {route.total_duration_minutes} min
        </span>
      </div>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          <div className="space-y-1">
            {route.stops.map((stop) => (
              <SortableStop
                key={`${stop.property_id}-${stop.sequence}`}
                stop={stop}
                techColor={route.tech_color}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  );
}

export default function RouteEditor({
  routes,
  onReorder,
}: RouteEditorProps) {
  return (
    <div className="space-y-4">
      {routes.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No routes yet. Run optimization to generate routes.
        </p>
      )}
      {routes.map((route) => (
        <TechColumn
          key={route.tech_id}
          route={route}
          onReorder={(oldIdx, newIdx) => onReorder(route.tech_id, oldIdx, newIdx)}
        />
      ))}
    </div>
  );
}
