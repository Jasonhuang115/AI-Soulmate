declare module "pixi-live2d-display/cubism2" {
  export const Live2DModel: {
    from: (source: string, options?: Record<string, unknown>) => Promise<Live2DModelInstance>;
    registerTicker: (ticker: unknown) => void;
  };
}

declare module "pixi-live2d-display/cubism4" {
  export const Live2DModel: {
    from: (source: string, options?: Record<string, unknown>) => Promise<Live2DModelInstance>;
    registerTicker: (ticker: unknown) => void;
  };
}

type Live2DModelInstance = {
  x: number;
  y: number;
  anchor: { set: (x: number, y: number) => void };
  scale: { x: number; y: number; set: (value: number) => void };
  width: number;
  height: number;
  motion: (group: string, index?: number, priority?: number) => Promise<boolean>;
  expression: (id?: string | number) => Promise<boolean>;
  internalModel: {
    on: (event: string, fn: () => void) => void;
    off: (event: string, fn: () => void) => void;
    updateNaturalMovements?: (dt: number, now: number) => void;
    coreModel: {
      setParamFloat: (id: string, value: number) => void;
    };
    motionManager: {
      on: (event: string, fn: () => void) => void;
      off: (event: string, fn: () => void) => void;
      expressionManager?: {
        setExpression: (name: string) => void;
        resetExpression?: () => void;
      };
    };
  };
};
