import type {
  MultiCalculation,
  MultiCalculationRow,
  UnderlyingWorkspace,
} from "@/lib/api/types";

export type ProductViewRow = {
  relationshipId: string;
  symbol: string;
  leverageFactor: string;
  inverse: boolean;
  close: string | null;
  status: "AVAILABLE" | "UNAVAILABLE";
  theoreticalTarget: string | null;
};

export function buildProductViewRows(
  workspace: UnderlyingWorkspace,
  calculation: MultiCalculation | null,
): ProductViewRow[] {
  const calculations = new Map<string, MultiCalculationRow>(
    calculation?.rows.map((row) => [row.relationship.id, row]) ?? [],
  );
  return workspace.rows.map((row) => {
    const calculated = calculations.get(row.relationship.id);
    const status = calculated?.status ?? row.status;
    return {
      relationshipId: row.relationship.id,
      symbol: row.relationship.leveraged_product.symbol,
      leverageFactor: row.relationship.leverage_factor,
      inverse: row.relationship.direction === "INVERSE",
      close: row.anchor?.leveraged_product.close ?? null,
      status,
      theoreticalTarget:
        status === "AVAILABLE"
          ? (calculated?.theoretical_target_price ?? null)
          : null,
    };
  });
}

export function normalizedSearchQuery(value: string): string {
  return value.trim().slice(0, 64);
}
