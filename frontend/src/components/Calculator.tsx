import React, { useReducer } from 'react';
import '../styles/calculator.css';
import { CLEARED, isOperator, pressKey } from '../utils/calculator';

const KEYS = ['7', '8', '9', '/', '4', '5', '6', '*', '1', '2', '3', '-', '0', '.', '=', '+'];

// The characters a narrow sidebar's display holds; a longer number is drawn
// smaller there (calculator.css), so its sign and first digits never fall
// off its left edge.
const FITS_NARROW = 15;

const Calculator: React.FC = () => {
  const [state, press] = useReducer(pressKey, CLEARED);

  return (
    <div className="calculator">
      <div
        className={state.display.length > FITS_NARROW ? 'display display-long' : 'display'}
        role="status"
        aria-label="Calculator display"
      >
        {state.display}
      </div>
      <div className="buttons">
        {KEYS.map((key) => (
          <button
            key={key}
            type="button"
            className={key === '=' ? 'calc-eq' : isOperator(key) ? 'calc-op' : undefined}
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
