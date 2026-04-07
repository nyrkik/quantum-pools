"use client";

import { useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import DifficultyModal from "@/components/profitability/difficulty-modal";
import { PoolSidebar, PoolDetailPanel, ModeSwitcher, MapPanel } from "@/components/map";
import { useMapPageState } from "@/components/map/use-map-page-state";

export default function MapPage() {
  const searchParams = useSearchParams();
  const initialBowId = searchParams.get("wf");
  const s = useMapPageState(initialBowId);

  if (s.loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <ModeSwitcher
        mode={s.mode}
        onModeChange={s.setMode}
        analyzedCount={s.analyzedCount}
        totalBowCount={s.totalBowCount}
      />

      {/* 3-Column Layout: List | Map | Details */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4" style={{ height: "calc(100vh - 140px)", minHeight: 500 }}>
        {/* Left Panel */}
        <div className="lg:col-span-3 flex flex-col min-h-0">
          {s.mode === "pools" ? (
            <PoolSidebar
              search={s.search}
              onSearchChange={s.setSearch}
              typeFilter={s.typeFilter}
              onToggleType={s.toggleType}
              commercialGroups={s.commercialGroups}
              residentialGroups={s.residentialGroups}
              filteredGroups={s.filteredGroups}
              propertyGroups={s.propertyGroups}
              selectedPropertyId={s.selectedPropertyId}
              highlightedBowId={s.highlightedBowId}
              onPropertySelect={s.handlePropertySelect}
              onHighlightBow={s.setHighlightedBowId}
              listRef={s.listRef}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
              {s.mode === "routes" ? "Route list coming soon" : "Customer list coming soon"}
            </div>
          )}
        </div>

        {/* Center: Map */}
        <MapPanel
          filteredGroups={s.filteredGroups}
          selectedPropertyId={s.selectedPropertyId}
          pinPosition={s.movingProperty ? s.propertyPinPosition : s.pinPosition}
          shouldFlyTo={s.shouldFlyTo}
          mapActionsRef={s.mapActionsRef}
          onPropertySelect={s.handlePropertySelect}
          onPinPlace={s.handlePinPlace}
          onZoomChange={s.setMapZoom}
          mapZoom={s.mapZoom}
          pinDirty={s.pinDirty}
          onResetPin={() => s.setPinPosition(null)}
          statusFilters={s.statusFilters}
          onToggleFilter={s.toggleFilter}
        />

        {/* Right: Details Panel */}
        <div className="lg:col-span-4 min-h-0 overflow-y-auto">
          {s.mode !== "pools" ? (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              {s.mode === "routes" ? "Route details coming soon" : "Profitability details coming soon"}
            </div>
          ) : s.selectedGroup ? (
            <PoolDetailPanel
              selectedGroup={s.selectedGroup}
              selectedPropertyId={s.selectedPropertyId!}
              canEdit={s.canEdit}
              movingProperty={s.movingProperty}
              propertyPinPosition={s.propertyPinPosition}
              savingPropertyPin={s.savingPropertyPin}
              propDetail={s.propDetail}
              profitData={s.profitData}
              medians={s.medians}
              chemicalCosts={s.chemicalCosts}
              costExpanded={s.costExpanded}
              bowDetails={s.bowDetails}
              dimComparisons={s.dimComparisons}
              analysisMap={s.analysisMap}
              rateAllocation={s.rateAllocation}
              images={s.images}
              capturing={s.capturing}
              activeBowId={s.activeBowId}
              highlightedBowId={s.highlightedBowId}
              pinDirty={s.pinDirty}
              savingPin={s.savingPin}
              savingPerimeter={s.savingPerimeter}
              measuringPerimeterBow={s.measuringPerimeterBow}
              dismissedDiscrepancies={s.dismissedDiscrepancies}
              perimeterInputs={s.perimeterInputs}
              areaInputs={s.areaInputs}
              volumeInputs={s.volumeInputs}
              perimeterShapes={s.perimeterShapes}
              roundedCornersInputs={s.roundedCornersInputs}
              stepEntryInputs={s.stepEntryInputs}
              benchShelfInputs={s.benchShelfInputs}
              shallowDepthInputs={s.shallowDepthInputs}
              deepDepthInputs={s.deepDepthInputs}
              perms={s.perms}
              onSetMovingProperty={s.setMovingProperty}
              onSetPropertyPinPosition={s.setPropertyPinPosition}
              onSavePropertyLocation={s.savePropertyLocation}
              onSetCostExpanded={s.setCostExpanded}
              onSetDiffModalOpen={s.setDiffModalOpen}
              onHighlightBow={s.setHighlightedBowId}
              onSavePin={s.savePin}
              onSetMeasuringBow={s.setMeasuringPerimeterBow}
              onSetPerimeterInput={s.onSetPerimeterInput}
              onSetAreaInput={s.onSetAreaInput}
              onSetVolumeInput={s.onSetVolumeInput}
              onSetPerimeterShape={s.onSetPerimeterShape}
              onSetRoundedCorners={s.onSetRoundedCorners}
              onSetStepEntry={s.onSetStepEntry}
              onSetBenchShelf={s.onSetBenchShelf}
              onSetShallowDepth={s.onSetShallowDepth}
              onSetDeepDepth={s.onSetDeepDepth}
              onSaveMeasurements={s.saveMeasurements}
              onDismissDiscrepancy={s.handleDismissDiscrepancy}
              onUploadPhoto={s.uploadPhoto}
              onSetHero={s.setHero}
              onDeleteImage={s.deleteImage}
              onResetPinState={() => { s.setPinPosition(null); s.setPinDirty(false); }}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              Select a property from the list or map
            </div>
          )}
        </div>
      </div>

      {s.selectedPropertyId && (
        <DifficultyModal
          open={s.diffModalOpen}
          onOpenChange={s.setDiffModalOpen}
          propertyId={s.selectedPropertyId}
          bowDetail={s.selectedGroup?.wfs[0] ? (s.bowDetails.get(s.selectedGroup.wfs[0].id) || null) : null}
          onSaved={() => {
            if (s.selectedPropertyId && s.selectedGroup) {
              s.loadPropertyDetail(s.selectedPropertyId, s.selectedGroup.wfs);
            }
          }}
        />
      )}
    </div>
  );
}
