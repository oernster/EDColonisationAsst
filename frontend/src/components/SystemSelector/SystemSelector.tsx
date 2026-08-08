import { useState, useEffect } from 'react';
import { 
  Box, 
  TextField, 
  Autocomplete, 
  Typography, 
  Chip,
  CircularProgress 
} from '@mui/material';
import { useColonisationStore } from '../../stores/colonisationStore';
import { api } from '../../services/api';
import { apiErrorDetail } from '../../utils/apiError';

export const SystemSelector = () => {
  const { 
   currentSystem,
   allSystems,
   currentSystemInfo,
   settingsVersion,
   setCurrentSystem,
   setAllSystems,
   setSystemData,
   setCurrentSystemInfo,
   setLoading,
   setError,
 } = useColonisationStore();

 const [searchQuery, setSearchQuery] = useState('');
 const [loadingSystems, setLoadingSystems] = useState(false);

 // Load all known systems from the backend on mount (and when settings change).
 // Autocomplete filtering is then handled purely client-side by MUI.
 useEffect(() => {
   const loadSystems = async () => {
     try {
       setLoadingSystems(true);
        const systems = await api.getSystems();
        setAllSystems(systems);
       
       // Also get current system info
       const currentInfo = await api.getCurrentSystem();
       setCurrentSystemInfo(currentInfo);
       
       // Auto-select current system if available
       if (currentInfo.current_system && systems.includes(currentInfo.current_system)) {
         handleSystemSelect(currentInfo.current_system);
       }
     } catch (error) {
       console.error('Failed to load systems:', error);
       setError('Failed to load systems');
     } finally {
       setLoadingSystems(false);
     }
   };

   loadSystems();
   // handleSystemSelect is redefined every render, so listing it here would
   // re-run this effect on every render and refetch the system list each
   // time. The store setters are stable. This is a load-on-mount effect that
   // re-runs only when the settings version changes. That is the whole
   // dependency it has.
   // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [settingsVersion]);

 const handleSystemSelect = async (systemName: string | null) => {
   if (!systemName) {
      setCurrentSystem(null);
      setSystemData(null);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setCurrentSystem(systemName);
      
      const data = await api.getSystemData(systemName);
      setSystemData(data);
    } catch (error: unknown) {
      console.error('Failed to load system data:', error);
      setError(apiErrorDetail(error) || 'Failed to load system data');
      setSystemData(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box>
      <Autocomplete
        value={currentSystem}
        onChange={(_, newValue) => handleSystemSelect(newValue)}
        inputValue={searchQuery}
        onInputChange={(_, newInputValue) => setSearchQuery(newInputValue)}
        options={allSystems}
        loading={loadingSystems}
        noOptionsText="No known systems with colonisation data"
        renderInput={(params) => (
          <TextField
            {...params}
            label="Search System"
            placeholder="Type to search..."
            InputProps={{
              ...params.InputProps,
              endAdornment: (
                <>
                  {loadingSystems ? <CircularProgress color="inherit" size={20} /> : null}
                  {params.InputProps.endAdornment}
                </>
              ),
            }}
          />
        )}
        sx={{ mb: 2 }}
      />

      {currentSystemInfo?.current_system && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="body2" color="text.secondary">
            Current System:
          </Typography>
          <Chip
            label={currentSystemInfo.current_system}
            color="primary"
            size="small"
            onClick={() => handleSystemSelect(currentSystemInfo.current_system)}
          />
        </Box>
      )}
    </Box>
  );
};
