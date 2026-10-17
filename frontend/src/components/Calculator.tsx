import React, { useReducer } from 'react';
import '../styles/calculator.css';
import { CLEARED, OPERATORS, pressKey } from '../utils/calculator';

const KEYS = ['7', '8', '9', '/', '4', '5', '6', '*', '1', '2', '3', '-', '0', '.', '=', '+'];

const Calculator: React.FC = () => {
  const [state, press] = useReducer(pressKey, CLEARED);

  return (
    <div className="calculator">
      <div className="display" role="status" aria-label="Calculator display">{state.display}</div>
      <div className="buttons">
        {KEYS.map((key) => (
          <button
            key={key}
            type="button"
            className={key === '=' ? 'calc-eq' : OPERATORS.includes(key) ? 'calc-op' : undefined}
            onClick={() => press(key)}
          >
            {key}
          </button>
        ))}
        <button type="button" className="calc-clear" onClick={() => press('C')}>C</button>
      </div>
    </div>
  );
};

export default Calculator;
