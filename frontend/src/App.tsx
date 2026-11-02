import { css } from '../styled-system/css'
import { Center, Stack } from '../styled-system/jsx'

function App() {
  return (
    <Center minH="100vh" bg="gray.50" px="4">
      <Stack gap="4" textAlign="center" maxW="xl">
        <h1 className={css({ fontSize: '4xl', fontWeight: 'bold', color: 'gray.900' })}>
          eBilard
        </h1>
        <p className={css({ fontSize: 'lg', color: 'gray.600' })}>
          React + TypeScript + Panda CSS
        </p>
      </Stack>
    </Center>
  )
}

export default App
