import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { VariableNode as VariableNodeType } from "@/lib/causal-twin/graph";
import styles from "./TwinCanvas.module.css";

// One part of the child's days that a link connects (a Causal Twin variable).
// Links are not drawn by hand, so the handles are only anchor points.
export function VariableNode({ data }: NodeProps<VariableNodeType>) {
  const lr = data.direction === "LR";
  return (
    <div className={styles.node} data-variable={data.tag} data-focus={data.focus}>
      <Handle
        type="target"
        position={lr ? Position.Left : Position.Top}
        isConnectable={false}
        className={styles.handle}
      />
      <span className={styles.nodeLabel}>{data.label}</span>
      <Handle
        type="source"
        position={lr ? Position.Right : Position.Bottom}
        isConnectable={false}
        className={styles.handle}
      />
    </div>
  );
}
