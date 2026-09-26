import React, { useState } from 'react';
import '../styles/calculator.css';

/**
 * We used to define type Operation = '+' | '-' | '*' | '/' | null
 * locally. Now it's declared globally in global.d.ts.
 */

const Calculator: React.FC = () => {
  const [display, setDisplay] = useState<string>('0');
  const [currentOperation, setCurrentOperation] = useState<Operation>(null);
  const [previousValue, setPreviousValue] = useState<number | null>(null);

  const handleNumberClick = (number: string) => {
    setDisplay(prev => prev === '0' ? number : prev + number);
  };

  const handleOperationClick = (operation: Operation) => {
    setPreviousValue(parseFloat(display));
    setCurrentOperation(operation);
    setDisplay('0');
  };

  const handleEqualClick = () => {
    if (currentOperation && previousValue !== null) {
      let result: number;
      switch (currentOperation) {
        case '+':
          result = previousValue + parseFloat(display);
          break;
        case '-':
          result = previousValue - parseFloat(display);
          break;
        case '*':
          result = previousValue * parseFloat(display);
          break;
        case '/':
          result = previousValue / parseFloat(display);
          break;
        default:
          return;
      }
      setDisplay(result.toString());
      setCurrentOperation(null);
      setPreviousValue(null);
    }
  };

  const handleClearClick = () => {
    setDisplay('0');
    setCurrentOperation(null);
    setPreviousValue(null);
  };

  return (
    <div className="calculator">
      <div className="display" role="status" aria-label="Calculator display">{display}</div>
      <div className="buttons">
        {['7', '8', '9', '/', '4', '5', '6', '*', '1', '2', '3', '-', '0', '.', '=', '+'].map((btn, index) => (
          <button
            key={index}
            type="button"
            className={btn === '=' ? 'calc-eq' : ['+', '-', '*', '/'].includes(btn) ? 'calc-op' : undefined}
            onClick={() => {
              if (btn === '=') handleEqualClick();
              else if (['+', '-', '*', '/'].includes(btn)) {
                handleOperationClick(btn as Operation);
              } else {
                handleNumberClick(btn);
              }
            }}
          >
            {btn}
          </button>
        ))}
        <button type="button" className="calc-clear" onClick={handleClearClick}>C</button>
      </div>
    </div>
  );
};

export default Calculator;
