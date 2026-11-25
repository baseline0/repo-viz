import App from './App.svelte';

const target = document.getElementById('app');
if (!target) throw new Error('#app not found');

new App({ target });
