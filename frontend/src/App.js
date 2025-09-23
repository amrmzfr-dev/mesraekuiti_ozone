import './global.css';
import Auth from './components/Auth';
import { BrowserRouter as Router } from 'react-router-dom';

function App() {
  return (
    <Router>
      <div className="App">
        <Auth />
      </div>
    </Router>
  );
}

export default App;
