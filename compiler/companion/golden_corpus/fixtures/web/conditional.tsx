<layout>
  {someValue ? <label value={'yes'} /> : <label value={'no'} />}
  {!hideView || <view />}
  {when(showExtra, () => {
    <view />
  })}
</layout>
