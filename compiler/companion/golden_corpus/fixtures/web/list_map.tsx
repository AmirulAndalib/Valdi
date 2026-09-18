const items = ['a', 'b', 'c'];
<element
  sections={items.map((section) => {
    return {
      key: section,
      onRenderHeader: () => {
        <label value={section} />
      },
      onRenderBody: () => {
        <layout>
          <view />
        </layout>
      },
    }
  })}
/>
