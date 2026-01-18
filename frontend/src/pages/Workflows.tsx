import { useState, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Workflow,
  Play,
  Circle,
  Square,
  GitBranch,
  ChevronDown,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { workflowsApi } from '@/lib/api'

type WorkflowSummary = {
  id: string
  name: string
  description: string
  author: string
  node_count: number
  edge_count: number
}

type WorkflowNode = {
  id: string
  intent: string
  preferred_actions: string[]
  type: string
  position: { x: number; y: number }
}

type WorkflowEdge = {
  id: string
  source: string
  target: string | Record<string, string>
  type: string
  state_key?: string
  comment?: string
}

export function Workflows() {
  const navigate = useNavigate()
  const [selectedWorkflow, setSelectedWorkflow] = useState<string | null>(null)

  const { data: workflowsData, isLoading } = useQuery({
    queryKey: ['workflows'],
    queryFn: workflowsApi.list,
  })

  const { data: workflowDetail } = useQuery({
    queryKey: ['workflow', selectedWorkflow],
    queryFn: () => workflowsApi.get(selectedWorkflow!),
    enabled: !!selectedWorkflow,
  })

  const workflows = workflowsData?.workflows || []

  // Auto-select first workflow when loaded
  useEffect(() => {
    if (workflows.length > 0 && !selectedWorkflow) {
      setSelectedWorkflow(workflows[0].id)
    }
  }, [workflows, selectedWorkflow])

  // Calculate canvas bounds from nodes
  const canvasBounds = useMemo(() => {
    if (!workflowDetail?.nodes?.length) return { width: 800, height: 400 }

    let maxX = 0
    let maxY = 0
    workflowDetail.nodes.forEach((node: WorkflowNode) => {
      maxX = Math.max(maxX, node.position.x + 200) // node width + padding
      maxY = Math.max(maxY, node.position.y + 100) // node height + padding
    })
    return { width: Math.max(800, maxX + 50), height: Math.max(400, maxY + 50) }
  }, [workflowDetail])

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="border-b border-border shrink-0">
        <div className="px-4 py-3 flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate('/dashboard')}>
            <ArrowLeft className="h-5 w-5" />
          </Button>

          <div className="flex items-center gap-3">
            <Workflow className="h-5 w-5 text-primary" />
            <span className="text-lg font-semibold">Workflows</span>
          </div>

          <div className="h-6 w-px bg-border mx-2" />

          {/* Workflow Selector Dropdown */}
          {isLoading ? (
            <span className="text-sm text-muted-foreground">Loading...</span>
          ) : workflows.length === 0 ? (
            <span className="text-sm text-muted-foreground">No workflows found</span>
          ) : (
            <div className="relative">
              <select
                value={selectedWorkflow || ''}
                onChange={(e) => setSelectedWorkflow(e.target.value)}
                className="appearance-none bg-background border border-input rounded-md px-3 py-2 pr-8 text-sm font-medium shadow-sm hover:bg-accent focus:outline-none focus:ring-1 focus:ring-ring cursor-pointer"
              >
                {workflows.map((workflow: WorkflowSummary) => (
                  <option key={workflow.id} value={workflow.id}>
                    {workflow.name} ({workflow.node_count} nodes)
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 h-4 w-4 pointer-events-none text-muted-foreground" />
            </div>
          )}

          {/* Workflow info and actions */}
          {workflowDetail && (
            <>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-muted-foreground truncate">
                  {workflowDetail.description}
                </p>
              </div>

              <Button size="sm" variant="outline">
                <Play className="h-4 w-4 mr-1" />
                Test
              </Button>
            </>
          )}
        </div>
      </header>

      {/* Full-width canvas area */}
      <main className="flex-1 overflow-auto p-4">
        {workflowDetail ? (
          <>
          <div className="relative bg-muted/30 rounded-lg min-h-full overflow-auto">
            <svg
              className="absolute inset-0 pointer-events-none"
              style={{ width: canvasBounds.width, height: canvasBounds.height }}
            >
              {/* Draw edges */}
              {workflowDetail.edges.map((edge: WorkflowEdge) => {
                const sourceNode = workflowDetail.nodes.find(
                  (n: WorkflowNode) => n.id === edge.source
                )
                const targets =
                  typeof edge.target === 'string'
                    ? [edge.target]
                    : Object.values(edge.target)

                return targets.map((targetId, i) => {
                  const targetNode = workflowDetail.nodes.find(
                    (n: WorkflowNode) => n.id === targetId
                  )
                  if (!sourceNode || !targetNode) return null

                  const x1 = sourceNode.position.x + 80
                  const y1 = sourceNode.position.y + 25
                  const x2 = targetNode.position.x
                  const y2 = targetNode.position.y + 25

                  return (
                    <g key={`${edge.id}-${i}`}>
                      <path
                        d={`M ${x1} ${y1} C ${x1 + 50} ${y1}, ${x2 - 50} ${y2}, ${x2} ${y2}`}
                        fill="none"
                        stroke={edge.type === 'condition' ? '#f59e0b' : '#6b7280'}
                        strokeWidth="2"
                        markerEnd="url(#arrowhead)"
                      />
                    </g>
                  )
                })
              })}
              <defs>
                <marker
                  id="arrowhead"
                  markerWidth="10"
                  markerHeight="7"
                  refX="9"
                  refY="3.5"
                  orient="auto"
                >
                  <polygon points="0 0, 10 3.5, 0 7" fill="#6b7280" />
                </marker>
              </defs>
            </svg>

            {/* Draw nodes */}
            <div className="relative" style={{ width: canvasBounds.width, height: canvasBounds.height }}>
              {workflowDetail.nodes.map((node: WorkflowNode) => (
                <div
                  key={node.id}
                  className="absolute"
                  style={{
                    left: node.position.x,
                    top: node.position.y,
                    width: '160px',
                  }}
                >
                  <div
                    className={`p-3 rounded-lg border-2 bg-background shadow-sm ${
                      node.type === 'start'
                        ? 'border-green-500'
                        : node.type === 'end'
                        ? 'border-red-500'
                        : 'border-border'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      {node.type === 'start' ? (
                        <Circle className="h-3 w-3 text-green-500 fill-green-500" />
                      ) : node.type === 'end' ? (
                        <Square className="h-3 w-3 text-red-500 fill-red-500" />
                      ) : (
                        <GitBranch className="h-3 w-3 text-primary" />
                      )}
                      <span className="text-xs font-medium truncate">{node.id}</span>
                    </div>
                    <p className="text-xs text-muted-foreground line-clamp-2">
                      {node.intent.slice(0, 60)}...
                    </p>
                    {node.preferred_actions.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {node.preferred_actions.slice(0, 2).map((action) => (
                          <span
                            key={action}
                            className="text-[10px] px-1.5 py-0.5 bg-primary/10 text-primary rounded"
                          >
                            {action}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

          </div>

          {/* State Variables - below canvas */}
          {workflowDetail.state_schema &&
            Object.keys(workflowDetail.state_schema).length > 0 && (
              <div className="mt-4 bg-muted/30 border rounded-lg p-3">
                <h3 className="text-xs font-medium mb-2 text-muted-foreground">State Variables</h3>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(workflowDetail.state_schema).map(
                    ([key, schema]: [string, any]) => (
                      <span
                        key={key}
                        className="text-xs px-2 py-0.5 bg-background rounded border"
                        title={`Type: ${schema.type}, Default: ${schema.default}`}
                      >
                        {key}: {schema.type}
                      </span>
                    )
                  )}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <div className="text-center">
              <Workflow className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Select a workflow to view</p>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
