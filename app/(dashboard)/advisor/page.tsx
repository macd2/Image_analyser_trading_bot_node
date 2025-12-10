'use client'

import { useState, useEffect } from 'react'
import { Brain, RefreshCw, Plus, Settings, Activity, Database, Edit, Trash2, AlertTriangle } from 'lucide-react'
import { LoadingState, ErrorState } from '@/components/shared'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from '@/components/ui/table'

interface AdvisorStrategy {
  id: string
  name: string
  description: string
  version: string
  config_schema: any
  created_at: string
}

interface AdvisorNode {
  id: string
  instance_id: string
  strategy_id: string
  config: any
  enabled: boolean
  execution_order: number
  created_at: string
  strategy_name?: string
}

interface AdvisorInstanceSettings {
  instance_id: string
  strategy_id: string
  config: any
  enabled: boolean
}

export default function AdvisorPage() {
  const [strategies, setStrategies] = useState<AdvisorStrategy[]>([])
  const [nodes, setNodes] = useState<AdvisorNode[]>([])
  const [instanceSettings, setInstanceSettings] = useState<AdvisorInstanceSettings[]>([])
  const [loading, setLoading] = useState(true)
  const [error] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [selectedInstance, setSelectedInstance] = useState<string | null>(null)
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null)
  const [isCreateNodeDialogOpen, setIsCreateNodeDialogOpen] = useState(false)
  const [isEditNodeDialogOpen, setIsEditNodeDialogOpen] = useState(false)
  const [isCreateStrategyDialogOpen, setIsCreateStrategyDialogOpen] = useState(false)
  const [editingNode, setEditingNode] = useState<AdvisorNode | null>(null)
  const [newNodeConfig, setNewNodeConfig] = useState<any>({})
  const [newStrategy, setNewStrategy] = useState<Partial<AdvisorStrategy>>({
    name: '',
    description: '',
    version: '1.0',
    config_schema: {}
  })

  // Mock data for demonstration
  useEffect(() => {
    // Simulate loading
    const timer = setTimeout(() => {
      setStrategies([
        {
          id: 'alex_top_down',
          name: 'Alex Top-Down Analysis',
          description: 'Top-down analysis across timeframes with Area of Interest and Entry Signals',
          version: '1.0',
          config_schema: {},
          created_at: new Date().toISOString()
        },
        {
          id: 'market_regime_check',
          name: 'Market Regime Detection',
          description: 'Higher timeframe bias, volume-validated candlestick patterns, market structure shift confirmation',
          version: '1.0',
          config_schema: {},
          created_at: new Date().toISOString()
        }
      ])

      setNodes([
        {
          id: 'node1',
          instance_id: 'instance1',
          strategy_id: 'alex_top_down',
          config: { timeframes: ['1h', '4h', '1d'] },
          enabled: true,
          execution_order: 1,
          created_at: new Date().toISOString(),
          strategy_name: 'Alex Top-Down Analysis'
        },
        {
          id: 'node2',
          instance_id: 'instance1',
          strategy_id: 'market_regime_check',
          config: { volume_threshold: 1.5 },
          enabled: true,
          execution_order: 2,
          created_at: new Date().toISOString(),
          strategy_name: 'Market Regime Detection'
        }
      ])

      setInstanceSettings([
        {
          instance_id: 'instance1',
          strategy_id: 'alex_top_down',
          config: {},
          enabled: true
        }
      ])

      setLoading(false)
      setRefreshing(false)
    }, 1000)

    return () => clearTimeout(timer)
  }, [])

  const handleCreateNode = async () => {
    if (!selectedInstance || !selectedStrategy) {
      alert('Please select both an instance and a strategy')
      return
    }

    const newNode = {
      id: `node${nodes.length + 1}`,
      instance_id: selectedInstance,
      strategy_id: selectedStrategy,
      config: newNodeConfig,
      enabled: true,
      execution_order: nodes.length + 1,
      created_at: new Date().toISOString(),
      strategy_name: strategies.find(s => s.id === selectedStrategy)?.name || 'Unknown'
    }

    setNodes([...nodes, newNode])
    setIsCreateNodeDialogOpen(false)
    setNewNodeConfig({})
  }

  const handleUpdateNode = async () => {
    if (!editingNode) return

    setNodes(nodes.map(node =>
      node.id === editingNode.id ? {
        ...node,
        config: newNodeConfig,
        execution_order: editingNode.execution_order
      } : node
    ))

    setIsEditNodeDialogOpen(false)
    setEditingNode(null)
    setNewNodeConfig({})
  }

  const handleDeleteNode = async (nodeId: string) => {
    if (!confirm('Are you sure you want to delete this advisor node?')) return

    setNodes(nodes.filter(node => node.id !== nodeId))
  }

  const handleToggleNode = async (nodeId: string, enabled: boolean) => {
    setNodes(nodes.map(node =>
      node.id === nodeId ? { ...node, enabled: !enabled } : node
    ))
  }

  const handleCreateStrategy = async () => {
    const newStrategyId = `strategy${strategies.length + 1}`

    setStrategies([...strategies, {
      id: newStrategyId,
      name: newStrategy.name || 'New Strategy',
      description: newStrategy.description || '',
      version: newStrategy.version || '1.0',
      config_schema: newStrategy.config_schema || {},
      created_at: new Date().toISOString()
    }])

    setIsCreateStrategyDialogOpen(false)
    setNewStrategy({
      name: '',
      description: '',
      version: '1.0',
      config_schema: {}
    })
  }

  if (loading) return <LoadingState text="Loading advisor configuration..." />
  if (error) return <ErrorState message={error} onRetry={() => setLoading(true)} />

  // Group nodes by instance
  const nodesByInstance = nodes.reduce((acc, node) => {
    if (!acc[node.instance_id]) {
      acc[node.instance_id] = []
    }
    acc[node.instance_id].push(node)
    return acc
  }, {} as Record<string, AdvisorNode[]>)

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            🧠 Advisor System
            <Badge variant="secondary" className="ml-2">
              {strategies.length} strategies
            </Badge>
            <Badge variant="secondary">
              {nodes.length} nodes
            </Badge>
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Technical Analysis Advisor for AI Enhancement
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setLoading(true);
              setRefreshing(true);
            }}
            disabled={refreshing}
            className="p-2 rounded-lg bg-slate-700 hover:bg-slate-600 transition disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`w-5 h-5 text-slate-300 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
          <Button
            onClick={() => setIsCreateStrategyDialogOpen(true)}
            className="flex items-center gap-2"
          >
            <Plus className="w-5 h-5" />
            New Strategy
          </Button>
          <Button
            onClick={() => setIsCreateNodeDialogOpen(true)}
            className="flex items-center gap-2"
          >
            <Plus className="w-5 h-5" />
            New Node
          </Button>
        </div>
      </div>

      {/* Warning Banner */}
      <Card className="bg-yellow-900/20 border-yellow-700">
        <div className="p-4 flex items-start gap-3">
          <AlertTriangle className="w-6 h-6 text-yellow-500 flex-shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h3 className="font-semibold text-yellow-300">Prototype – Mock Data Only</h3>
            <p className="text-yellow-200/80 text-sm">
              This advisor UI is a prototype and currently displays mock data. The integration with the backtest engine and live trading is under development.
              <br />
              <span className="text-yellow-300/70 text-xs">
                See integration roadmap for details.
              </span>
            </p>
          </div>
        </div>
      </Card>
      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Strategies Card */}
        <Card className="bg-slate-800 border-slate-700">
          <div className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <Brain className="w-5 h-5" />
                Strategies
              </h3>
              <Badge variant="secondary">{strategies.length}</Badge>
            </div>
            <Separator className="bg-slate-700 mb-4" />
            <div className="space-y-3">
              {strategies.map((strategy) => (
                <div key={strategy.id} className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-700 transition">
                  <div className="flex items-center gap-3">
                    <div className="w-3 h-3 rounded-full bg-blue-500" />
                    <div>
                      <div className="font-medium text-white">{strategy.name}</div>
                      <div className="text-xs text-slate-400">{strategy.version}</div>
                    </div>
                  </div>
                  <div className="text-xs text-slate-400 max-w-[200px] truncate">
                    {strategy.description}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>

        {/* Nodes by Instance Card */}
        <Card className="bg-slate-800 border-slate-700">
          <div className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <Activity className="w-5 h-5" />
                Node Distribution
              </h3>
              <Badge variant="secondary">{Object.keys(nodesByInstance).length} instances</Badge>
            </div>
            <Separator className="bg-slate-700 mb-4" />
            <div className="space-y-3">
              {Object.entries(nodesByInstance).map(([instanceId, instanceNodes]) => (
                <div key={instanceId} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="font-medium text-white text-sm truncate max-w-[150px]">
                      {instanceId}
                    </div>
                    <Badge variant="secondary">{instanceNodes.length} nodes</Badge>
                  </div>
                  <div className="ml-4 space-y-1">
                    {instanceNodes.map((node) => (
                      <div key={node.id} className="flex items-center gap-2 text-xs">
                        <div className={`w-2 h-2 rounded-full ${node.enabled ? 'bg-green-500' : 'bg-red-500'}`} />
                        <span className="text-slate-300 truncate max-w-[120px]">{node.strategy_name}</span>
                        <span className="text-slate-500">#{node.execution_order}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>

        {/* Instance Settings Card */}
        <Card className="bg-slate-800 border-slate-700">
          <div className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <Settings className="w-5 h-5" />
                Instance Settings
              </h3>
              <Badge variant="secondary">{instanceSettings.length} configured</Badge>
            </div>
            <Separator className="bg-slate-700 mb-4" />
            <div className="space-y-3">
              {instanceSettings.map((setting) => (
                <div key={setting.instance_id} className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-700 transition">
                  <div className="flex items-center gap-3">
                    <div className="w-3 h-3 rounded-full bg-green-500" />
                    <div>
                      <div className="font-medium text-white text-sm truncate max-w-[150px]">
                        {setting.instance_id}
                      </div>
                      <div className="text-xs text-slate-400">
                        {strategies.find(s => s.id === setting.strategy_id)?.name || 'Unknown'}
                      </div>
                    </div>
                  </div>
                  <Badge variant={setting.enabled ? "default" : "secondary"}>
                    {setting.enabled ? "Enabled" : "Disabled"}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>

      {/* Detailed Nodes Table */}
      <Card className="bg-slate-800 border-slate-700">
        <div className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-white flex items-center gap-2">
              <Database className="w-5 h-5" />
              Advisor Nodes Configuration
            </h3>
            <div className="flex items-center gap-2">
              <Select value={selectedInstance || ''} onValueChange={setSelectedInstance}>
                <SelectTrigger className="w-[180px] bg-slate-700 border-slate-600">
                  <SelectValue placeholder="Filter by instance" />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700">
                  <SelectItem value="all">All Instances</SelectItem>
                  {Object.keys(nodesByInstance).map((instanceId) => (
                    <SelectItem key={instanceId} value={instanceId}>{instanceId}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <Separator className="bg-slate-700 mb-4" />
          <div className="rounded-md border border-slate-700">
            <Table>
              <TableHeader className="bg-slate-700">
                <TableRow>
                  <TableHead className="text-slate-300">Status</TableHead>
                  <TableHead className="text-slate-300">Instance</TableHead>
                  <TableHead className="text-slate-300">Strategy</TableHead>
                  <TableHead className="text-slate-300">Order</TableHead>
                  <TableHead className="text-slate-300">Config</TableHead>
                  <TableHead className="text-slate-300">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {nodes
                  .filter(node => !selectedInstance || selectedInstance === 'all' || node.instance_id === selectedInstance)
                  .map((node) => (
                    <TableRow key={node.id} className="hover:bg-slate-700/50">
                      <TableCell>
                        <Switch
                          checked={node.enabled}
                          onCheckedChange={() => handleToggleNode(node.id, node.enabled)}
                          className="data-[state=checked]:bg-green-500 data-[state=unchecked]:bg-slate-600"
                        />
                      </TableCell>
                      <TableCell className="font-medium text-white">
                        <div className="truncate max-w-[150px]">{node.instance_id}</div>
                      </TableCell>
                      <TableCell className="text-slate-300">
                        {node.strategy_name}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">#{node.execution_order}</Badge>
                      </TableCell>
                      <TableCell className="text-slate-400 text-sm">
                        <div className="truncate max-w-[200px]">
                          {JSON.stringify(node.config)}
                        </div>
                      </TableCell>
                      <TableCell className="flex items-center gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-blue-400 hover:text-blue-300"
                          onClick={() => {
                            setEditingNode(node)
                            setNewNodeConfig(node.config)
                            setIsEditNodeDialogOpen(true)
                          }}
                        >
                          <Edit className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-400 hover:text-red-300"
                          onClick={() => handleDeleteNode(node.id)}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </Card>

      {/* Create Node Dialog */}
      <Dialog open={isCreateNodeDialogOpen} onOpenChange={setIsCreateNodeDialogOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 max-w-md">
          <DialogHeader>
            <DialogTitle className="text-white">Create New Advisor Node</DialogTitle>
            <DialogDescription className="text-slate-400">
              Configure a new TA strategy node for an instance
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <div className="text-sm font-medium text-slate-300">Instance</div>
              <Select value={selectedInstance || ''} onValueChange={setSelectedInstance}>
                <SelectTrigger className="bg-slate-700 border-slate-600">
                  <SelectValue placeholder="Select instance" />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700">
                  {Object.keys(nodesByInstance).map((instanceId) => (
                    <SelectItem key={instanceId} value={instanceId}>{instanceId}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <div className="text-sm font-medium text-slate-300">Strategy</div>
              <Select value={selectedStrategy || ''} onValueChange={setSelectedStrategy}>
                <SelectTrigger className="bg-slate-700 border-slate-600">
                  <SelectValue placeholder="Select strategy" />
                </SelectTrigger>
                <SelectContent className="bg-slate-800 border-slate-700">
                  {strategies.map((strategy) => (
                    <SelectItem key={strategy.id} value={strategy.id}>
                      {strategy.name} ({strategy.version})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <div className="text-sm font-medium text-slate-300">Configuration</div>
              <div className="bg-slate-700 border-slate-600 rounded-md p-2 text-sm">
                {JSON.stringify(newNodeConfig, null, 2)}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsCreateNodeDialogOpen(false)}
              className="border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateNode}
              className="bg-blue-600 hover:bg-blue-700"
              disabled={!selectedInstance || !selectedStrategy}
            >
              Create Node
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Node Dialog */}
      <Dialog open={isEditNodeDialogOpen} onOpenChange={setIsEditNodeDialogOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 max-w-md">
          <DialogHeader>
            <DialogTitle className="text-white">Edit Advisor Node</DialogTitle>
            <DialogDescription className="text-slate-400">
              Modify node configuration and settings
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {editingNode && (
              <>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-slate-300">Instance</div>
                  <div className="bg-slate-700 border-slate-600 rounded-md p-2">
                    {editingNode.instance_id}
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-slate-300">Strategy</div>
                  <div className="bg-slate-700 border-slate-600 rounded-md p-2">
                    {editingNode.strategy_name}
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-slate-300">Execution Order</div>
                  <div className="bg-slate-700 border-slate-600 rounded-md p-2">
                    {editingNode.execution_order}
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="text-sm font-medium text-slate-300">Configuration</div>
                  <div className="bg-slate-700 border-slate-600 rounded-md p-2 text-sm">
                    {JSON.stringify(newNodeConfig, null, 2)}
                  </div>
                </div>
                <div className="flex items-center gap-2 pt-2">
                  <Switch
                    id="enabled"
                    checked={editingNode.enabled}
                    onCheckedChange={(checked) => {
                      if (editingNode) {
                        setEditingNode({
                          ...editingNode,
                          enabled: checked
                        })
                      }
                    }}
                    className="data-[state=checked]:bg-green-500 data-[state=unchecked]:bg-slate-600"
                  />
                  <div className="text-sm text-slate-300">Enabled</div>
                </div>
              </>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setIsEditNodeDialogOpen(false)
                setEditingNode(null)
                setNewNodeConfig({})
              }}
              className="border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              Cancel
            </Button>
            <Button
              onClick={handleUpdateNode}
              className="bg-blue-600 hover:bg-blue-700"
              disabled={!editingNode}
            >
              Update Node
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Strategy Dialog */}
      <Dialog open={isCreateStrategyDialogOpen} onOpenChange={setIsCreateStrategyDialogOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 max-w-md">
          <DialogHeader>
            <DialogTitle className="text-white">Create New Strategy</DialogTitle>
            <DialogDescription className="text-slate-400">
              Define a new TA strategy for the advisor system
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <div className="text-sm font-medium text-slate-300">Name</div>
              <input
                value={newStrategy.name || ''}
                onChange={(e) => setNewStrategy({...newStrategy, name: e.target.value})}
                placeholder="e.g., Alex Top-Down Analysis"
                className="w-full bg-slate-700 border-slate-600 rounded-md p-2 text-sm"
              />
            </div>
            <div className="space-y-2">
              <div className="text-sm font-medium text-slate-300">Description</div>
              <input
                value={newStrategy.description || ''}
                onChange={(e) => setNewStrategy({...newStrategy, description: e.target.value})}
                placeholder="Brief description of the strategy"
                className="w-full bg-slate-700 border-slate-600 rounded-md p-2 text-sm"
              />
            </div>
            <div className="space-y-2">
              <div className="text-sm font-medium text-slate-300">Version</div>
              <input
                value={newStrategy.version || '1.0'}
                onChange={(e) => setNewStrategy({...newStrategy, version: e.target.value})}
                placeholder="1.0"
                className="w-full bg-slate-700 border-slate-600 rounded-md p-2 text-sm"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setIsCreateStrategyDialogOpen(false)
                setNewStrategy({
                  name: '',
                  description: '',
                  version: '1.0',
                  config_schema: {}
                })
              }}
              className="border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateStrategy}
              className="bg-blue-600 hover:bg-blue-700"
              disabled={!newStrategy.name || !newStrategy.description}
            >
              Create Strategy
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}